// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract MockDeFiProtocols {
    mapping(address => uint256) public balances;

    function flashloan(uint256 amount) external {}
    
    function swap(uint256 amount) external pure returns (uint256) {
        return amount + (amount / 100); // 1% arbitrage profit simulation
    }

    function deposit(uint256 amount) external {
        balances[msg.sender] += amount;
    }
}
