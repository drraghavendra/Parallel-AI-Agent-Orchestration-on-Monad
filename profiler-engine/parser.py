import re

class AdvancedSolidityASTProfiler:
    @staticmethod
    def deep_profile_source(code: str) -> dict:
        lines = code.split('\n')
        conflicts = []
        score = 100
        seen_findings = set()
        
        # State tracking matrices
        declared_global_arrays = []
        global_structs = {}
        
        def add_conflict(line_num, function_name, finding_type, severity, impact, remediation, penalty):
            nonlocal score
            dedupe_key = (line_num, function_name, finding_type)
            if dedupe_key in seen_findings:
                return

            seen_findings.add(dedupe_key)
            conflicts.append({
                "line": line_num,
                "function": function_name,
                "type": finding_type,
                "severity": severity,
                "impact": impact,
                "remediation": remediation
            })
            score -= penalty
        
        # Parse step 1: Map complex types that cause serialization bottlenecks
        for idx, line in enumerate(lines):
            clean_line = line.strip()
            
            # Find arrays that might be iterated over in state transitions
            array_match = re.search(r'([a-zA-Z0-9_]+)\[\]\s+(?:public|private|internal|external)?\s*([a-zA-Z0-9_]+);', clean_line)
            if array_match:
                declared_global_arrays.append(array_match.group(2))
                
            # Track shared system configuration storage patterns
            struct_match = re.search(r'struct\s+([a-zA-Z0-9_]+)\s*\{', clean_line)
            if struct_match:
                global_structs[struct_match.group(1)] = True

        # Parse step 2: Scan execution context functions for serialization anti-patterns
        current_function = None
        brace_depth = 0
        for idx, line in enumerate(lines):
            line_num = idx + 1
            clean_line = line.strip()
            
            function_match = re.search(r'function\s+([a-zA-Z0-9_]+)', clean_line)
            if function_match:
                current_function = function_match.group(1)
                brace_depth = clean_line.count('{') - clean_line.count('}')
            elif current_function:
                brace_depth += clean_line.count('{') - clean_line.count('}')
                if brace_depth < 0:
                    current_function = None
                    brace_depth = 0
                    continue
            
            if current_function:
                # 1. Look for un-sharded global sequential increments
                has_nonce_increment = re.search(r'\b[a-zA-Z0-9_]*(?:nonce|Nonce)\s*\+\+', clean_line)
                has_global_nonce_write = re.search(r'\bglobalNonce\s*(?:=|\+=|-=)', clean_line)
                if has_nonce_increment or has_global_nonce_write:
                    add_conflict(
                        line_num,
                        current_function,
                        "State-Lock Contention (SSTORE Serialization)",
                        "CRITICAL",
                        "Forces the scheduler to process transactions sequentially, neutralizing Monad's parallel speed advantage.",
                        "Deploy detached ERC-1167 isolated clone storage shards for each unique address framework.",
                        35
                    )

                # 2. Look for global metrics aggregators that cause write locks
                if re.search(r'\b(totalVolume|totalBalance)\s*(?:\+=|=\s*\1\s*\+)', clean_line):
                    add_conflict(
                        line_num,
                        current_function,
                        "Global Storage Bottleneck",
                        "HIGH",
                        "Concurrent execution paths are blocked by a shared write lock on this storage slot.",
                        "Convert the metric into a sharded layout (e.g., mapping(address => uint256)), and aggregate the data off-chain.",
                        25
                    )

                # 3. Look for loops over unbounded global state arrays
                for array_name in declared_global_arrays:
                    has_array_length_scan = f"{array_name}.length" in clean_line
                    has_for_loop_array_reference = "for" in clean_line and array_name in clean_line
                    if has_array_length_scan or has_for_loop_array_reference:
                        add_conflict(
                            line_num,
                            current_function,
                            "Unbounded State-Array Scan Loop",
                            "CRITICAL",
                            "O(N) reads over expanding arrays cause unpredictable execution delays and gas spikes.",
                            "Replace loop lookups with explicit mapping registries mapped to address keys.",
                            30
                        )

        return {
            "efficiency_score": max(score, 0),
            "status": "Production Parallel Ready" if score >= 85 else "Serialization Danger Warning",
            "detected_vulnerabilities_count": len(conflicts),
            "conflicts": conflicts
        }
