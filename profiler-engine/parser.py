import re

class AdvancedSolidityASTProfiler:
    @staticmethod
    def deep_profile_source(code: str) -> dict:
        lines = code.split('\n')
        conflicts = []
        score = 100
        
        # State tracking matrices
        declared_global_arrays = []
        global_structs = {}
        
        # Parse step 1: Map complex types that cause serialization bottlenecks
        for idx, line in enumerate(lines):
            line_num = idx + 1
            clean_line = line.strip()
            
            # Find arrays that might be iterated over in state transitions
            array_match = re.search(r'([a-zA-Z0-9_]+)\[\]\s+public\s+([a-zA-Z0-9_]+);', clean_line)
            if array_match:
                declared_global_arrays.append(array_match.group(2))
                
            # Track shared system configuration storage patterns
            struct_match = re.search(r'struct\s+([a-zA-Z0-9_]+)\s*\{', clean_line)
            if struct_match:
                global_structs[struct_match.group(1)] = True

        # Parse step 2: Scan execution context functions for serialization anti-patterns
        current_function = None
        for idx, line in enumerate(lines):
            line_num = idx + 1
            clean_line = line.strip()
            
            if "function " in clean_line:
                current_function = re.search(r'function\s+([a-zA-Z0-9_]+)', clean_line).group(1)
                
            if current_function:
                # 1. Look for un-sharded global sequential increments
                if re.search(r'(^[a-zA-Z0-9_]*nonce\s*\+\+|[a-zA-Z0-9_]*Nonce\s*\+\+)', clean_line) or "globalNonce" in clean_line:
                    conflicts.append({
                        "line": line_num,
                        "function": current_function,
                        "type": "State-Lock Contention (SSTORE Serialization)",
                        "severity": "CRITICAL",
                        "impact": "Forces the scheduler to process transactions sequentially, neutralizing Monad's parallel speed advantage.",
                        "remediation": "Deploy detached ERC-1167 isolated clone storage shards for each unique address framework."
                    })
                    score -= 35

                # 2. Look for global metrics aggregators that cause write locks
                if any(x in clean_line for x in ["totalVolume +=", "totalVolume = totalVolume +", "totalBalance += "]):
                    conflicts.append({
                        "line": line_num,
                        "function": current_function,
                        "type": "Global Storage Bottleneck",
                        "severity": "HIGH",
                        "impact": "Concurrent execution paths are blocked by a shared write lock on this storage slot.",
                        "remediation": "Convert the metric into a sharded layout (e.g., mapping(address => uint256)), and aggregate the data off-chain."
                    })
                    score -= 25

                # 3. Look for loops over unbounded global state arrays
                for array_name in declared_global_arrays:
                    if f"{array_name}.length" in clean_line or f"for" in clean_line and array_name in clean_line:
                        conflicts.append({
                            "line": line_num,
                            "function": current_function,
                            "type": "Unbounded State-Array Scan Loop",
                            "severity": "CRITICAL",
                            "impact": "O(N) reads over expanding arrays cause unpredictable execution delays and gas spikes.",
                            "remediation": "Replace loop lookups with explicit mapping registries mapped to address keys."
                        })
                        score -= 30

        return {
            "efficiency_score": max(score, 0),
            "status": "Production Parallel Ready" if score >= 85 else "Serialization Danger Warning",
            "detected_vulnerabilities_count": len(conflicts),
            "conflicts": conflicts
        }