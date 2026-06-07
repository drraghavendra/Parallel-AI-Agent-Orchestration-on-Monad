// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract PreOptimizedOrchestrator {
    struct SystemConfig {
        uint128 platformFeeBps;
        uint128 safetyBuffer;
        address treasury;
    }

    mapping(address => uint256) public agentBalances;
    address[] public registeredAgents; // Un-sharded global state iteration
    SystemConfig public globalConfig;
    uint256 public totalVolume;
    uint256 public globalNonce;

    event Executed(address indexed agent, uint256 amount, uint256 nonce);

    constructor(address _treasury) {
        globalConfig = SystemConfig(30, 100, _treasury);
    }

    // CRITICAL CONTENTION TRAP: 
    // Looping over a global state array and writing to tightly packed global config structs
    // completely stalls parallel schedulers due to write-locks on the same storage slots.
    function executeWorkflow(address agent, uint256 amount) external {
        globalNonce++;
        totalVolume += amount;
        
        bool exists = false;
        for(uint256 i = 0; i < registeredAgents.length; i++) {
            if(registeredAgents[i] == agent) {
                exists = true;
                break;
            }
        }
        if(!exists) {
            registeredAgents.push(agent);
        }

        uint256 fee = (amount * globalConfig.platformFeeBps) / 10000;
        agentBalances[agent] += (amount - fee);
        agentBalances[globalConfig.treasury] += fee;

        emit Executed(agent, amount, globalNonce);
    }
}
