import re
from collections import defaultdict
from pathlib import Path


class AdvancedSolidityASTProfiler:
    """Lightweight static Solidity profiler for Monad parallel-readiness and deployment confidence.

    Design constraints are intentional: no Solidity compiler, no Slither, no Docker,
    no blockchain calls, no database, and no heavyweight dependencies. The engine uses
    deterministic heuristics so the dashboard stays hackathon-friendly and local-only.
    """

    CATEGORY_LABELS = {
        "storage_isolation": "Storage Isolation",
        "write_contention": "Write Contention",
        "loop_scalability": "Loop Scalability",
        "sharding_readiness": "Sharding Readiness",
    }

    CATEGORY_EXPLANATIONS = {
        "Storage Isolation": "Measures whether frequently updated state is isolated per user/agent instead of shared across all transactions.",
        "Write Contention": "Measures the risk of many transactions writing to the same storage slot and forcing serialized execution.",
        "Loop Scalability": "Measures whether execution paths avoid unbounded scans over growing on-chain arrays.",
        "Sharding Readiness": "Measures how naturally the contract can adopt per-agent shards, mappings, or isolated storage lanes.",
    }

    CONFIDENCE_CATEGORY_LABELS = {
        "smart_contract_integrity": "Smart Contract Integrity",
        "deployment_readiness": "Deployment Readiness",
        "agent_reliability": "Agent Reliability",
        "profiler_accuracy": "Profiler Accuracy",
    }

    SEVERITY_PENALTIES = {
        "CRITICAL": 40,
        "HIGH": 20,
        "MEDIUM": 10,
        "LOW": 5,
    }

    RECOMMENDATION_TEMPLATES = {
        "global_nonce": {
            "issue": "Shared Global Nonce",
            "why_it_matters": "Multiple transactions write to the same nonce slot, forcing otherwise independent workflows into serialized execution.",
            "suggested_refactor": {
                "before": "uint256 public globalNonce;\n\nfunction executeWorkflow(...) external {\n    globalNonce++;\n}",
                "after": "mapping(address => uint256) public agentNonces;\n\nfunction executeWorkflow(...) external {\n    agentNonces[msg.sender]++;\n}",
            },
            "expected_benefit": "Reduces nonce hot-slot contention and improves parallel execution readiness.",
        },
        "global_counter": {
            "issue": "Global Storage Bottleneck",
            "why_it_matters": "Multiple transactions write to the same storage slot causing serialization.",
            "suggested_refactor": {
                "before": "uint256 public totalVolume;\n\nfunction executeWorkflow(uint256 amount) external {\n    totalVolume += amount;\n}",
                "after": "mapping(address => uint256) public shardedVolume;\n\nfunction executeWorkflow(uint256 amount) external {\n    shardedVolume[msg.sender] += amount;\n}",
            },
            "expected_benefit": "Reduces write contention and improves parallel execution.",
        },
        "shared_state": {
            "issue": "Shared State Variable",
            "why_it_matters": "A mutable contract-level variable can become a shared write target when many agents execute the same workflow.",
            "suggested_refactor": {
                "before": "uint256 public sharedMetric;\n\nfunction executeWorkflow(...) external {\n    sharedMetric += amount;\n}",
                "after": "mapping(address => uint256) public agentMetrics;\n\nfunction executeWorkflow(...) external {\n    agentMetrics[msg.sender] += amount;\n}",
            },
            "expected_benefit": "Isolates frequently updated state by agent and reduces dependency overlap between unrelated transactions.",
        },
        "array_scan": {
            "issue": "Unbounded Array Scan",
            "why_it_matters": "Loops over growing state arrays create O(N) reads and unpredictable gas, making parallel scheduling less efficient.",
            "suggested_refactor": {
                "before": "address[] public registeredAgents;\n\nfor (uint256 i = 0; i < registeredAgents.length; i++) {\n    if (registeredAgents[i] == agent) { ... }\n}",
                "after": "mapping(address => bool) public isRegisteredAgent;\n\nif (!isRegisteredAgent[agent]) {\n    isRegisteredAgent[agent] = true;\n}",
            },
            "expected_benefit": "Replaces linear scans with constant-time lookups as the number of agents grows.",
        },
        "centralized_registry": {
            "issue": "Centralized Registry",
            "why_it_matters": "A single registry array or list can become a coordination hotspot when many agents register or query membership.",
            "suggested_refactor": {
                "before": "address[] public registeredAgents;\nregisteredAgents.push(agent);",
                "after": "mapping(address => bool) public isRegisteredAgent;\nisRegisteredAgent[agent] = true;",
            },
            "expected_benefit": "Avoids centralized membership scans and improves registry scalability.",
        },
        "shared_mutable_storage": {
            "issue": "Shared Mutable Storage",
            "why_it_matters": "Mutable global state updated inside hot execution paths creates dependency overlap across independent transactions.",
            "suggested_refactor": {
                "before": "State public globalState;\nglobalState.value = newValue;",
                "after": "mapping(address => State) public agentState;\nagentState[msg.sender].value = newValue;",
            },
            "expected_benefit": "Moves writes into isolated storage lanes and reduces scheduler conflicts.",
        },
    }

    @staticmethod
    def deep_profile_source(code: str) -> dict:
        lines = code.split("\n")
        contract_name = AdvancedSolidityASTProfiler._extract_contract_name(code)
        state_context = AdvancedSolidityASTProfiler._collect_state_context(lines)
        readiness = AdvancedSolidityASTProfiler._analyze_parallel_readiness(lines, state_context)
        confidence = AdvancedSolidityASTProfiler._analyze_deployment_confidence(code, contract_name)

        category_scores = readiness["category_scores"]
        display_category_scores = {
            label: category_scores[key]
            for key, label in AdvancedSolidityASTProfiler.CATEGORY_LABELS.items()
        }
        category_explanations = {
            label: AdvancedSolidityASTProfiler.CATEGORY_EXPLANATIONS[label]
            for label in display_category_scores
        }
        overall_score = AdvancedSolidityASTProfiler._calculate_parallel_score(category_scores)
        severity_counts = AdvancedSolidityASTProfiler._severity_counts(readiness["conflicts"])
        readiness_classification = AdvancedSolidityASTProfiler._classify_parallel_readiness(overall_score)
        executive_summary = AdvancedSolidityASTProfiler._generate_executive_summary(
            contract_name=contract_name,
            overall_score=overall_score,
            classification=readiness_classification,
            conflicts=readiness["conflicts"],
            confidence=confidence,
            severity_counts=severity_counts,
        )

        return {
            "contract_name": contract_name,
            "analysis_timestamp": AdvancedSolidityASTProfiler._analysis_timestamp(),
            "overall_score": overall_score,
            "parallel_readiness_score": overall_score,
            "efficiency_score": overall_score,  # Backward compatibility for older UI callers.
            "parallel_readiness_classification": readiness_classification,
            "status": readiness_classification,
            "category_scores": display_category_scores,
            "category_score_keys": category_scores,
            "category_explanations": category_explanations,
            "detected_vulnerabilities_count": len(readiness["conflicts"]),
            "severity_counts": severity_counts,
            "conflicts": readiness["conflicts"],
            "storage_conflict_map": AdvancedSolidityASTProfiler._build_conflict_map(readiness["conflicts"]),
            "executive_summary": executive_summary,
            "deployment_confidence": confidence,
        }

    @staticmethod
    def _collect_state_context(lines: list) -> dict:
        arrays = []
        mappings = []
        scalar_variables = {}
        registry_candidates = []

        for line in lines:
            clean_line = AdvancedSolidityASTProfiler._strip_inline_comment(line.strip())
            if not clean_line:
                continue

            array_match = re.search(
                r"([A-Za-z0-9_]+)\[\]\s+(?:public|private|internal|external)?\s*([A-Za-z0-9_]+)\s*;",
                clean_line,
            )
            if array_match:
                name = array_match.group(2)
                arrays.append(name)
                if re.search(r"registered|registry|agents|users|members", name, re.IGNORECASE):
                    registry_candidates.append(name)
                continue

            mapping_match = re.search(r"mapping\s*\((.*?)=>\s*(.*?)\)\s+(?:public|private|internal)?\s*([A-Za-z0-9_]+)", clean_line)
            if mapping_match:
                mappings.append(mapping_match.group(3))
                continue

            state_var_match = re.search(
                r"\b(?:uint\d*|int\d*|address|bool|bytes\d*|string)\s+(?:public|private|internal|external)?\s*([A-Za-z0-9_]+)\s*;",
                clean_line,
            )
            if state_var_match:
                scalar_variables[state_var_match.group(1)] = clean_line.split()[0]

        return {
            "arrays": arrays,
            "mappings": mappings,
            "scalar_variables": scalar_variables,
            "registry_candidates": registry_candidates,
        }

    @staticmethod
    def _analyze_parallel_readiness(lines: list, state_context: dict) -> dict:
        conflicts = []
        seen_findings = set()
        category_scores = {
            "storage_isolation": 100,
            "write_contention": 100,
            "loop_scalability": 100,
            "sharding_readiness": 100,
        }

        def add_conflict(line_num, function_name, finding_type, severity, impact, remediation, storage_target, recommendation_key, penalties, detection_confidence):
            dedupe_key = (line_num, function_name, finding_type, storage_target)
            if dedupe_key in seen_findings:
                return
            seen_findings.add(dedupe_key)

            for category, penalty in penalties.items():
                category_scores[category] = AdvancedSolidityASTProfiler._clamp(category_scores[category] - penalty)

            recommendation = AdvancedSolidityASTProfiler._build_recommendation(recommendation_key)
            conflicts.append({
                "line": line_num,
                "function": function_name,
                "type": finding_type,
                "severity": severity,
                "impact": impact,
                "remediation": remediation,
                "storage_target": storage_target,
                "conflict_type": recommendation["issue"],
                "recommendation_template": recommendation_key,
                "suggestion_template": recommendation_key,  # Backward compatible field name.
                "recommendation": recommendation,
                "suggestion": recommendation,  # Backward compatible field name.
                "detection_confidence": detection_confidence,
                "detection_confidence_label": f"{detection_confidence}%",
            })

        current_function = None
        brace_depth = 0
        for idx, line in enumerate(lines):
            line_num = idx + 1
            clean_line = AdvancedSolidityASTProfiler._strip_inline_comment(line.strip())
            if not clean_line:
                continue

            function_match = re.search(r"function\s+([A-Za-z0-9_]+)", clean_line)
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

            nonce_match = re.search(r"\b([A-Za-z0-9_]*(?:nonce|Nonce))\s*\+\+", clean_line)
            global_nonce_write = re.search(r"\b(globalNonce)\s*(?:=|\+=|-=)", clean_line)
            if nonce_match or global_nonce_write:
                storage_target = (nonce_match or global_nonce_write).group(1)
                add_conflict(
                    line_num,
                    current_function,
                    "State-Lock Contention",
                    "CRITICAL",
                    "Shared nonce mutation can force independent transactions to wait on the same storage slot.",
                    "Use per-agent nonce mappings or isolated shard-local nonce counters.",
                    storage_target,
                    "global_nonce",
                    {"storage_isolation": 25, "write_contention": 35, "sharding_readiness": 25},
                    92,
                )

            counter_match = re.search(r"\b(totalVolume|totalBalance|totalDeposits|totalSupply)\s*(?:\+=|=\s*\1\s*\+)", clean_line)
            if counter_match:
                storage_target = counter_match.group(1)
                add_conflict(
                    line_num,
                    current_function,
                    "Global Storage Bottleneck",
                    "HIGH",
                    "Concurrent execution paths are blocked by a shared write lock on this aggregate storage slot.",
                    "Convert the aggregate into a per-agent mapping and aggregate off-chain or on a slower path.",
                    storage_target,
                    "global_counter",
                    {"storage_isolation": 15, "write_contention": 30, "sharding_readiness": 20},
                    85,
                )

            for array_name in state_context["arrays"]:
                has_array_length_scan = f"{array_name}.length" in clean_line
                has_for_loop_array_reference = "for" in clean_line and array_name in clean_line
                if has_array_length_scan or has_for_loop_array_reference:
                    add_conflict(
                        line_num,
                        current_function,
                        "Array Scan Serialization Risk",
                        "CRITICAL",
                        "O(N) scans over expanding arrays create gas unpredictability and scheduler-unfriendly execution paths.",
                        "Replace array membership checks with mapping-based registries.",
                        array_name,
                        "array_scan",
                        {"loop_scalability": 45, "storage_isolation": 10, "sharding_readiness": 15},
                        78,
                    )

            for registry_name in state_context["registry_candidates"]:
                if re.search(rf"\b{re.escape(registry_name)}\.push\s*\(", clean_line):
                    add_conflict(
                        line_num,
                        current_function,
                        "Centralized Registry Mutation",
                        "HIGH",
                        "A centralized registry array can become a coordination hotspot as participants grow.",
                        "Use mapping(address => bool) registries for membership and emit events for off-chain indexing.",
                        registry_name,
                        "centralized_registry",
                        {"storage_isolation": 10, "loop_scalability": 20, "sharding_readiness": 15},
                        80,
                    )

            for variable_name in state_context["scalar_variables"]:
                if variable_name in {"globalNonce", "totalVolume", "totalBalance", "totalDeposits", "totalSupply"}:
                    continue
                shared_write_match = re.search(rf"\b{re.escape(variable_name)}\s*(?:=|\+=|-=|\+\+|--)", clean_line)
                if shared_write_match:
                    add_conflict(
                        line_num,
                        current_function,
                        "Shared Mutable Storage Write",
                        "MEDIUM",
                        "A contract-level mutable variable is updated inside an execution path and may become shared state pressure.",
                        "Move frequently updated state into mappings or isolated storage shards.",
                        variable_name,
                        "shared_mutable_storage",
                        {"storage_isolation": 10, "write_contention": 15, "sharding_readiness": 10},
                        70,
                    )

        return {"conflicts": conflicts, "category_scores": category_scores}

    @staticmethod
    def _analyze_deployment_confidence(code: str, contract_name: str) -> dict:
        deductions = []
        category_scores = {
            "smart_contract_integrity": 100,
            "deployment_readiness": 100,
            "agent_reliability": 100,
            "profiler_accuracy": 100,
        }

        def add_deduction(category, issue, impact, recommendation, expected_gain, evidence):
            penalty = AdvancedSolidityASTProfiler.SEVERITY_PENALTIES[impact]
            category_scores[category] = AdvancedSolidityASTProfiler._clamp(category_scores[category] - penalty)
            deductions.append({
                "category": AdvancedSolidityASTProfiler.CONFIDENCE_CATEGORY_LABELS[category],
                "category_key": category,
                "issue": issue,
                "impact": impact,
                "confidence_penalty": -penalty,
                "recommendation": recommendation,
                "expected_confidence_gain": f"+{expected_gain}",
                "expected_confidence_gain_value": expected_gain,
                "evidence": evidence,
            })

        # Smart contract layer heuristics.
        if re.search(r"function\s+flashloanCallback\s*\(", code) and not re.search(r"msg\.sender\s*==\s*(?:flashloanPool|trustedFlashloanPool|authorizedPool|owner)", code):
            add_deduction(
                "smart_contract_integrity",
                "flashloanCallback callable by anyone",
                "CRITICAL",
                "Restrict callback execution using protocol-only access control or a verified trusted pool address.",
                40,
                "flashloanCallback has no obvious msg.sender authorization check.",
            )

        if "assembly" in code and "create2" in code and "0x37" in code:
            add_deduction(
                "smart_contract_integrity",
                "Manual clone deployment bytecode requires verification",
                "HIGH",
                "Add tests that validate EIP-1167 bytecode, deterministic addresses, and initialization behavior.",
                20,
                "create2 minimal proxy bytecode is manually assembled.",
            )

        if re.search(r"transfer\(msg\.sender,\s*loanAmount\)", code):
            add_deduction(
                "smart_contract_integrity",
                "Repayment logic sends funds to callback caller",
                "HIGH",
                "Validate the flashloan lender address and ensure repayment targets the trusted pool, not an arbitrary caller.",
                20,
                "Repayment uses msg.sender inside callback.",
            )

        if "IMockProtocol" in code and "flashloan(uint256 amount, bytes calldata data)" in code:
            mock_protocol_path = AdvancedSolidityASTProfiler._project_root() / "contracts" / "src" / "MockDeFiProtocols.sol"
            mock_code = AdvancedSolidityASTProfiler._safe_read(mock_protocol_path)
            if mock_code and "function flashloan(uint256 amount)" in mock_code:
                add_deduction(
                    "smart_contract_integrity",
                    "Interface mismatch between orchestrator and mock protocol",
                    "HIGH",
                    "Align MockDeFiProtocols.flashloan with IMockProtocol.flashloan(uint256, bytes) or update the interface.",
                    20,
                    "IMockProtocol expects flashloan(uint256,bytes) but mock contract exposes flashloan(uint256).",
                )

        # Infrastructure layer heuristics.
        deploy_script = AdvancedSolidityASTProfiler._project_root() / "contracts" / "scripts" / "Deploy.s.sol"
        if not AdvancedSolidityASTProfiler._safe_read(deploy_script).strip():
            add_deduction(
                "deployment_readiness",
                "Empty deployment script",
                "HIGH",
                "Complete the Foundry deployment script with deterministic deployment and address output.",
                20,
                "contracts/scripts/Deploy.s.sol is empty.",
            )

        foundry_config = AdvancedSolidityASTProfiler._project_root() / "contracts" / "foundry.toml"
        if not AdvancedSolidityASTProfiler._safe_read(foundry_config).strip():
            add_deduction(
                "deployment_readiness",
                "Missing Foundry configuration",
                "HIGH",
                "Populate foundry.toml with source, output, optimizer, and test configuration.",
                20,
                "contracts/foundry.toml is empty.",
            )

        # Agent layer heuristics.
        agent_code = AdvancedSolidityASTProfiler._safe_read(AdvancedSolidityASTProfiler._project_root() / "agent-layer" / "orchestrator_agent.js")
        if re.search(r"0x[a-fA-F0-9]{40}", agent_code):
            add_deduction(
                "agent_reliability",
                "Hardcoded Ethereum addresses in agent layer",
                "MEDIUM",
                "Move addresses into a local config file or environment variables for safer demos.",
                10,
                "Agent layer contains literal 20-byte addresses.",
            )

        if "getTransactionCount(this.wallet.address, \"pending\")" in agent_code and "Promise.all(operationalPipelines)" in agent_code:
            add_deduction(
                "agent_reliability",
                "Nonce collision risk under concurrent dispatch",
                "HIGH",
                "Use a nonce manager or serialized nonce allocator per wallet before dispatching concurrent pipelines.",
                20,
                "Concurrent Promise.all dispatches share pending nonce lookup logic.",
            )

        if "MAX_RETRIES = 3" in agent_code:
            add_deduction(
                "agent_reliability",
                "Limited transaction retry strategy",
                "LOW",
                "Add structured retry telemetry, idempotency guards, and configurable retry limits.",
                5,
                "Retry count is hardcoded to 3.",
            )

        # Profiler layer heuristics.
        add_deduction(
            "profiler_accuracy",
            "Static regex-based profiler has heuristic limits",
            "LOW",
            "Label findings as heuristic, keep detection confidence visible, and validate critical findings with tests before production use.",
            5,
            "Profiler intentionally avoids compilation and full AST analysis.",
        )

        display_scores = {
            label: category_scores[key]
            for key, label in AdvancedSolidityASTProfiler.CONFIDENCE_CATEGORY_LABELS.items()
        }
        overall_confidence = round(sum(category_scores.values()) / len(category_scores))
        classification = AdvancedSolidityASTProfiler._classify_deployment_confidence(overall_confidence)
        roadmap = AdvancedSolidityASTProfiler._build_confidence_roadmap(overall_confidence, deductions)

        return {
            "overall_score": overall_confidence,
            "confidence_score": overall_confidence,
            "classification": classification,
            "category_scores": display_scores,
            "category_score_keys": category_scores,
            "deductions": sorted(deductions, key=lambda item: abs(item["confidence_penalty"]), reverse=True),
            "roadmap": roadmap,
            "purpose": "Measures project safety for deployment, demonstration, and production usage independently from Parallel Readiness.",
        }

    @staticmethod
    def _build_confidence_roadmap(current_score: int, deductions: list) -> dict:
        sorted_actions = sorted(deductions, key=lambda item: item["expected_confidence_gain_value"], reverse=True)
        top_actions = [
            {
                "rank": index + 1,
                "action": item["recommendation"],
                "issue": item["issue"],
                "potential_gain": item["expected_confidence_gain"],
                "potential_gain_value": item["expected_confidence_gain_value"],
            }
            for index, item in enumerate(sorted_actions[:5])
        ]
        projected_score = min(100, current_score + sum(action["potential_gain_value"] for action in top_actions))
        return {
            "title": "Top Actions To Reach Production Readiness",
            "current_confidence": current_score,
            "projected_confidence": projected_score,
            "actions": top_actions,
        }

    @staticmethod
    def _build_recommendation(template_key: str) -> dict:
        template = AdvancedSolidityASTProfiler.RECOMMENDATION_TEMPLATES[template_key]
        return {
            "issue": template["issue"],
            "why_it_matters": template["why_it_matters"],
            "suggested_refactor": template["suggested_refactor"],
            "expected_benefit": template["expected_benefit"],
        }

    @staticmethod
    def _build_conflict_map(conflicts: list) -> list:
        grouped_targets = defaultdict(list)
        for conflict in conflicts:
            function_name = conflict.get("function") or "unknownFunction"
            entry = {
                "storage_target": conflict.get("storage_target") or "unknownStorage",
                "conflict_type": conflict.get("conflict_type") or conflict.get("type") or "Unknown Conflict",
                "severity": conflict.get("severity", "LOW"),
                "detection_confidence": conflict.get("detection_confidence", 0),
            }
            if entry not in grouped_targets[function_name]:
                grouped_targets[function_name].append(entry)

        return [
            {"function": function_name, "storage_targets": targets}
            for function_name, targets in grouped_targets.items()
        ]

    @staticmethod
    def _generate_executive_summary(contract_name: str, overall_score: int, classification: str, conflicts: list, confidence: dict, severity_counts: dict) -> str:
        if not conflicts:
            return (
                f"{contract_name} is classified as {classification} with no detected storage serialization bottlenecks. "
                f"Deployment Confidence is {confidence['overall_score']}/100 ({confidence['classification']}); review the confidence roadmap before production use."
            )

        risk_count = severity_counts.get("CRITICAL", 0) + severity_counts.get("HIGH", 0)
        most_critical = next((item for item in conflicts if item.get("severity") == "CRITICAL"), conflicts[0])
        number_word = AdvancedSolidityASTProfiler._number_word(risk_count)
        return (
            f"{contract_name} contains {number_word} high-risk serialization bottlenecks that may significantly reduce Monad parallel execution efficiency. "
            f"The most critical issue is {most_critical.get('conflict_type', most_critical.get('type'))} on {most_critical.get('storage_target', 'shared storage')}. "
            f"Parallel Readiness is {overall_score}/100 ({classification}), while Deployment Confidence is {confidence['overall_score']}/100 ({confidence['classification']}). "
            "Adopting storage sharding and mapping-based registries could substantially improve concurrency."
        )

    @staticmethod
    def _classify_parallel_readiness(score: int) -> str:
        if score >= 90:
            return "Production Parallel Ready"
        if score >= 75:
            return "Strong Parallel Candidate"
        if score >= 50:
            return "Needs Optimization"
        return "Serialization Risk"

    @staticmethod
    def _classify_deployment_confidence(score: int) -> str:
        if score >= 90:
            return "Production Ready"
        if score >= 75:
            return "Demo Ready"
        if score >= 50:
            return "Needs Improvements"
        return "Not Safe To Deploy"

    @staticmethod
    def _calculate_parallel_score(category_scores: dict) -> int:
        weights = {
            "storage_isolation": 0.30,
            "write_contention": 0.30,
            "loop_scalability": 0.20,
            "sharding_readiness": 0.20,
        }
        return round(sum(category_scores[key] * weight for key, weight in weights.items()))

    @staticmethod
    def _severity_counts(conflicts: list) -> dict:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for conflict in conflicts:
            severity = conflict.get("severity", "LOW")
            counts[severity] = counts.get(severity, 0) + 1
        return counts

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
    def _analysis_timestamp() -> str:
        # UTC-like ISO string without extra dependencies; frontend report also includes local generation time.
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _project_root() -> Path:
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def _safe_read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, value))

    @staticmethod
    def _number_word(value: int) -> str:
        words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
        return words.get(value, str(value))
