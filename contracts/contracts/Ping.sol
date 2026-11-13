// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title Ping
 * @notice Trivial contract for walking skeleton smoke testing.
 */
contract Ping is Ownable {
    event Pong(address indexed sender, uint256 timestamp);

    constructor() Ownable(msg.sender) {}

    function ping() external returns (string memory) {
        emit Pong(msg.sender, block.timestamp);
        return "pong";
    }

    function pong() external pure returns (string memory) {
        return "ping";
    }
}
