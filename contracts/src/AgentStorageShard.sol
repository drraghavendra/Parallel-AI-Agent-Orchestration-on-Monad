// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract AgentStorageShard {
    // Packed into Slot 0 to minimize SSTORE execution gas costs
    address public orchestrator;
    uint96 public localNonce;

    // Packed into Slot 1
    address public agentOwner;
    bool public initialized;

    // Separate slots for independent financial metric tracking
    uint256 public localBalance;
    uint256 public localCumulativeVolume;

    modifier onlyOrchestrator() {
        require(msg.sender == orchestrator, "Unauthorized access: Caller must be orchestrator");
        _;
    }

    // Replaced standard constructor with an initialization function to support ERC-1167 Clone architecture
    function initialize(address _orchestrator, address _agentOwner) external {
        require(!initialized, "Shard already initialized");
        orchestrator = _orchestrator;
        agentOwner = _agentOwner;
        initialized = true;
    }

    function recordExecution(uint256 amount) external onlyOrchestrator {
        unchecked {
            localNonce++;
            localCumulativeVolume += amount;
        }
        localBalance += amount;
    }

    function withdrawLiquidity(address token, address to, uint256 amount) external onlyOrchestrator {
        // High-performance direct lower-level call to bypass contract bloat
        (bool success, ) = token.call(abi.encodeWithSignature("transfer(address,uint256)", to, amount));
        require(success, "Token extraction failed");
    }
}
