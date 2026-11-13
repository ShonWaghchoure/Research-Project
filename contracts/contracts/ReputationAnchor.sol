// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/**
 * @title ReputationAnchor
 * @notice Stores per-interval Merkle roots of reputation leaves for off-chain verification.
 */
contract ReputationAnchor is AccessControl {
    bytes32 public constant OPERATOR_ROLE = keccak256("OPERATOR_ROLE");

    /// @dev intervalId => merkle root
    mapping(uint256 => bytes32) public roots;

    event RootPosted(uint256 indexed intervalId, bytes32 root);

    /**
     * @param admin Role admin.
     * @param operator Account allowed to post roots.
     */
    constructor(address admin, address operator) {
        require(admin != address(0), "ReputationAnchor: admin");
        require(operator != address(0), "ReputationAnchor: operator");
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(OPERATOR_ROLE, operator);
    }

    /**
     * @notice Post the reputation Merkle root for an interval (once).
     * @param id Interval identifier.
     * @param root Merkle root of reputation leaves.
     */
    function postRoot(uint256 id, bytes32 root) external onlyRole(OPERATOR_ROLE) {
        require(root != bytes32(0), "ReputationAnchor: empty root");
        require(roots[id] == bytes32(0), "ReputationAnchor: already posted");
        roots[id] = root;
        emit RootPosted(id, root);
    }

    /**
     * @notice Verify a reputation leaf against the posted root.
     * @param id Interval identifier.
     * @param participant Participant address.
     * @param scoreBp Reputation score in basis points (uint16).
     * @param evidenceCount Evidence counter committed in the leaf.
     * @param proof Merkle proof (sibling hashes).
     * @return True if the leaf is in the tree.
     */
    function verifyScore(
        uint256 id,
        address participant,
        uint16 scoreBp,
        uint32 evidenceCount,
        bytes32[] calldata proof
    ) external view returns (bool) {
        bytes32 root = roots[id];
        require(root != bytes32(0), "ReputationAnchor: no root");
        bytes32 leaf = keccak256(abi.encodePacked(participant, scoreBp, evidenceCount));
        return MerkleProof.verify(proof, root, leaf);
    }
}
