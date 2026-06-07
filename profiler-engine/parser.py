import re
from collections import defaultdict


class AdvancedSolidityASTProfiler:
    """Lightweight static Solidity profiler for Monad parallel-readiness signals.

    This intentionally avoids compilation, AST dependencies, Slither, blockchain calls,
    and databases. It uses deterministic pattern matching to preserve the project's
    hackathon-friendly architecture while returning a richer report contract.
    """

    CATEGORY_LABELS = {
        "storage_isolation": "Storage Isolation",
        "write_contention": "Write Contention",
        "loop_scalability": "Loop Scalability",
        "sharding_readiness": "Sharding Readiness",
    }

    SUGGESTION_TEMPLATES = {
        "global_nonce": {
            "issue": "Shared Global Nonce",
            "why_it_matters": "Multiple transactions write to the same nonce slot, forcing otherwise independent workflows into serialized execution.",
            "suggested_refactor": {
                "before": "uint256 public globalNonce;\n\nfunction executeWorkflow(...) external {\n    globalNonce++;\n}",
                "after": "mapping(address => uint256) public agentNonces;\n\nfunction executeWorkflow(...) external {\n    agentNonces[msg.sender]++;\n}",
            },
            "expected_benefit": "Moves nonce updates into per-agent storage, reducing hot-slot contention and improving concurrent execution readiness.",
        },
        "global_counter": {
            "issue": "Global Storage Bottleneck",
            "why_it_matters": "Multiple transactions write to the same storage slot causing serialization.",
            "suggested_refactor": {
                "before": "uint256 public totalVolume;\n\nfunction executeWorkflow(uint256 amount) external {\n    totalVolume += amount;\n}",
                "after": "mapping(address => uint256) public shardedVolume;\n\nfunction executeWorkflow(uint256 amount) external {\n    shardedVolume[msg.sender] += amount;\n}",
            },
            "expected_benefit": "Reduces storage contention and improves parallel execution by making volume accounting agent-local.",
        },
        "shared_state": {
            "issue": "Shared State Variable",
            "why_it_matters": "A mutable contract-level variable can become a shared write target when many agents execute the same workflow.",
            "suggested_refactor": {
                "before": "SystemConfig public globalConfig;\nuint256 public sharedMetric;",
                "after": "mapping(address => AgentConfig) public agentConfigs;\nmapping(address => uint256) public agentMetrics;",
            },
            "expected_benefit": "Isolates frequently updated state by agent, limiting dependency overlap between unrelated transactions.",
        },
        "array_scan": {
            "issue": "Unbounded Array Scan",
            "why_it_matters": "Loops over growing state arrays create O(N) reads and unpredictable gas, making parallel scheduling less efficient.",
            "suggested_refactor": {
                "before": "address[] public registeredAgents;\n\nfor (uint256 i = 0; i < registeredAgents.length; i++) {\n    if (registeredAgents[i] == agent) { ... }\n}",
                "after": "mapping(address => bool) public isRegisteredAgent;\n\nif (!isRegisteredAgent[agent]) {\n    isRegisteredAgent[agent] = true;\n}",
            },
            "expected_benefit": "Replaces linear scans with constant-time lookups, improving scalability as the number of agents grows.",
        },
    }

    @staticmethod
    def deep_profile_source(code: str) -> dict:
        lines = code.split("\n")
        conflicts = []
        seen_findings = set()

        # State tracking matrices used by the lightweight scanner.
        declared_global_arrays = []
        declared_state_variables = {}
        contract_name = AdvancedSolidityASTProfiler._extract_contract_name(code)

        category_scores = {
            "storage_isolation": 100,
            "write_contention": 100,
            "loop_scalability": 100,
            "sharding_readiness": 100,
        }

        def clamp_score(value: int) -> int:
            return max(0, min(100, value))

        def apply_penalties(penalties: dict) -> None:
            for category, penalty in penalties.items():
                category_scores[category] = clamp_score(category_scores[category] - penalty)

        def add_conflict(
            line_num: int,
            function_name: str,
            finding_type: str,
            severity: str,
            impact: str,
            remediation: str,
            storage_target: str,
            suggestion_key: str,
            category_penalties: dict,
        ) -> None:
            dedupe_key = (line_num, function_name, finding_type, storage_target)
            if dedupe_key in seen_findings:
                return

            seen_findings.add(dedupe_key)
            suggestion = AdvancedSolidityASTProfiler._build_suggestion(suggestion_key)
            conflicts.append({
                "line": line_num,
                "function": function_name,
                "type": finding_type,
                "severity": severity,
                "impact": impact,
                "remediation": remediation,
                "storage_target": storage_target,
                "suggestion_template": suggestion_key,
                "suggestion": suggestion,
            })
            apply_penalties(category_penalties)

        # Parse step 1: Map state declarations that can become scheduler hotspots.
        for line in lines:
            clean_line = AdvancedSolidityASTProfiler._strip_inline_comment(line.strip())
            if not clean_line:
                continue

            array_match = re.search(
                r"([a-zA-Z0-9_]+)\[\]\s+(?:public|private|internal|external)?\s*([a-zA-Z0-9_]+)\s*;",
                clean_line,
            )
            if array_match:
                array_name = array_match.group(2)
                declared_global_arrays.append(array_name)
                declared_state_variables[array_name] = {
                    "kind": "array",
                    "type": f"{array_match.group(1)}[]",
                }
                continue

            state_var_match = re.search(
                r"\b(?:uint\d*|int\d*|address|bool|bytes\d*|string)\s+(?:public|private|internal|external)?\s*([a-zA-Z0-9_]+)\s*;",
                clean_line,
            )
            if state_var_match:
                declared_state_variables[state_var_match.group(1)] = {
                    "kind": "scalar",
                    "type": clean_line.split()[0],
                }

        # Parse step 2: Scan execution context functions for serialization anti-patterns.
        current_function = None
        brace_depth = 0
        for idx, line in enumerate(lines):
            line_num = idx + 1
            clean_line = AdvancedSolidityASTProfiler._strip_inline_comment(line.strip())
            if not clean_line:
                continue

            function_match = re.search(r"function\s+([a-zA-Z0-9_]+)", clean_line)
            if function_match:
                current_function = function_match.group(1)
                brace_depth = clean_line.count("{") - clean_line.count("}")
            elif current_function:
                brace_depth += clean_line.count("{") - clean_line.count("}")
                if brace_depth < 0:
                    current_function = None
                    brace_depth = 0
                    continue

            if not current_function:
                continue

            # 1. Look for un-sharded global sequential increments.
            nonce_match = re.search(r"\b([a-zA-Z0-9_]*(?:nonce|Nonce))\s*\+\+", clean_line)
            global_nonce_write = re.search(r"\b(globalNonce)\s*(?:=|\+=|-=)", clean_line)
            if nonce_match or global_nonce_write:
                storage_target = (nonce_match or global_nonce_write).group(1)
                add_conflict(
                    line_num=line_num,
                    function_name=current_function,
                    finding_type="State-Lock Contention (SSTORE Serialization)",
                    severity="CRITICAL",
                    impact="Forces the scheduler to process transactions sequentially, neutralizing Monad's parallel speed advantage.",
                    remediation="Deploy detached ERC-1167 isolated clone storage shards or per-agent nonce mappings.",
                    storage_target=storage_target,
                    suggestion_key="global_nonce",
                    category_penalties={
                        "storage_isolation": 25,
                        "write_contention": 35,
                        "sharding_readiness": 25,
                    },
                )

            # 2. Look for global metrics aggregators that cause write locks.
            counter_match = re.search(r"\b(totalVolume|totalBalance)\s*(?:\+=|=\s*\1\s*\+)", clean_line)
            if counter_match:
                storage_target = counter_match.group(1)
                add_conflict(
                    line_num=line_num,
                    function_name=current_function,
                    finding_type="Global Storage Bottleneck",
                    severity="HIGH",
                    impact="Concurrent execution paths are blocked by a shared write lock on this storage slot.",
                    remediation="Convert the metric into a sharded layout (e.g., mapping(address => uint256)), and aggregate the data off-chain.",
                    storage_target=storage_target,
                    suggestion_key="global_counter",
                    category_penalties={
                        "storage_isolation": 15,
                        "write_contention": 30,
                        "sharding_readiness": 20,
                    },
                )

            # 3. Look for loops over unbounded global state arrays.
            for array_name in declared_global_arrays:
                has_array_length_scan = f"{array_name}.length" in clean_line
                has_for_loop_array_reference = "for" in clean_line and array_name in clean_line
                if has_array_length_scan or has_for_loop_array_reference:
                    add_conflict(
                        line_num=line_num,
                        function_name=current_function,
                        finding_type="Unbounded State-Array Scan Loop",
                        severity="CRITICAL",
                        impact="O(N) reads over expanding arrays cause unpredictable execution delays and gas spikes.",
                        remediation="Replace loop lookups with explicit mapping registries mapped to address keys.",
                        storage_target=array_name,
                        suggestion_key="array_scan",
                        category_penalties={
                            "loop_scalability": 45,
                            "storage_isolation": 10,
                            "sharding_readiness": 15,
                        },
                    )

            # 4. Detect generic shared state writes to known scalar variables.
            for variable_name, metadata in declared_state_variables.items():
                if metadata["kind"] != "scalar" or variable_name in {"globalNonce", "totalVolume", "totalBalance"}:
                    continue

                shared_write_match = re.search(rf"\b{re.escape(variable_name)}\s*(?:=|\+=|-=|\+\+|--)", clean_line)
                if shared_write_match and not re.search(r"mapping\s*\(", clean_line):
                    add_conflict(
                        line_num=line_num,
                        function_name=current_function,
                        finding_type="Shared State Variable Write",
                        severity="MEDIUM",
                        impact="A contract-level mutable variable is updated inside an execution path and may become a shared dependency across agents.",
                        remediation="Move frequently updated state into per-agent mappings or isolated storage shards where possible.",
                        storage_target=variable_name,
                        suggestion_key="shared_state",
                        category_penalties={
                            "storage_isolation": 10,
                            "write_contention": 15,
                            "sharding_readiness": 10,
                        },
                    )

        display_category_scores = {
            label: category_scores[key]
            for key, label in AdvancedSolidityASTProfiler.CATEGORY_LABELS.items()
        }
        overall_score = AdvancedSolidityASTProfiler._calculate_overall_score(category_scores)
        severity_counts = AdvancedSolidityASTProfiler._severity_counts(conflicts)
        conflict_map = AdvancedSolidityASTProfiler._build_conflict_map(conflicts)
        executive_summary = AdvancedSolidityASTProfiler._generate_executive_summary(
            contract_name=contract_name,
            overall_score=overall_score,
            conflicts=conflicts,
            severity_counts=severity_counts,
        )

        return {
            "contract_name": contract_name,
            "overall_score": overall_score,
            "parallel_readiness_score": overall_score,
            "efficiency_score": overall_score,  # Backward compatible for existing UI callers.
            "category_scores": display_category_scores,
            "category_score_keys": category_scores,
            "status": "Production Parallel Ready" if overall_score >= 85 else "Serialization Danger Warning",
            "detected_vulnerabilities_count": len(conflicts),
            "severity_counts": severity_counts,
            "conflicts": conflicts,
            "storage_conflict_map": conflict_map,
            "executive_summary": executive_summary,
        }

    @staticmethod
    def _strip_inline_comment(line: str) -> str:
        return line.split("//", 1)[0].strip()

    @staticmethod
    def _extract_contract_name(code: str) -> str:
        contract_matches = re.findall(r"\b(contract|interface|library)\s+([A-Za-z_][A-Za-z0-9_]*)", code)
        for declaration_type, name in contract_matches:
            if declaration_type == "contract":
                return name
        return contract_matches[0][1] if contract_matches else "UnknownContract"

    @staticmethod
    def _build_suggestion(template_key: str) -> dict:
        template = AdvancedSolidityASTProfiler.SUGGESTION_TEMPLATES[template_key]
        return {
            "issue": template["issue"],
            "why_it_matters": template["why_it_matters"],
            "suggested_refactor": template["suggested_refactor"],
            "expected_benefit": template["expected_benefit"],
        }

    @staticmethod
    def _calculate_overall_score(category_scores: dict) -> int:
        weights = {
            "storage_isolation": 0.30,
            "write_contention": 0.30,
            "loop_scalability": 0.20,
            "sharding_readiness": 0.20,
        }
        weighted_score = sum(category_scores[key] * weight for key, weight in weights.items())
        return round(weighted_score)

    @staticmethod
    def _severity_counts(conflicts: list) -> dict:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for conflict in conflicts:
            severity = conflict.get("severity", "LOW")
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    @staticmethod
    def _build_conflict_map(conflicts: list) -> list:
        grouped_targets = defaultdict(list)
        for conflict in conflicts:
            function_name = conflict.get("function") or "unknownFunction"
            target = conflict.get("storage_target") or "unknownStorage"
            if target not in grouped_targets[function_name]:
                grouped_targets[function_name].append(target)

        return [
            {"function": function_name, "storage_targets": targets}
            for function_name, targets in grouped_targets.items()
        ]

    @staticmethod
    def _generate_executive_summary(contract_name: str, overall_score: int, conflicts: list, severity_counts: dict) -> str:
        if not conflicts:
            return (
                f"{contract_name} shows strong Monad parallel readiness with no detected storage serialization bottlenecks. "
                "The contract appears to use isolated or low-contention storage patterns for the scanned execution paths."
            )

        risk_count = severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
        most_critical = next(
            (conflict for conflict in conflicts if conflict.get("severity") == "CRITICAL"),
            conflicts[0],
        )
        risk_label = "high-risk serialization bottleneck" if risk_count == 1 else "high-risk serialization bottlenecks"

        return (
            f"{contract_name} contains {risk_count} {risk_label} that are likely to reduce Monad parallel execution efficiency. "
            f"The most critical issue is {most_critical.get('storage_target', 'shared storage')} in {most_critical.get('function', 'an execution path')}. "
            f"Overall Parallel Readiness Score is {overall_score}/100. "
            "Adopting storage sharding patterns could significantly improve concurrency."
        )
