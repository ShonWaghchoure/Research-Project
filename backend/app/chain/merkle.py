"""OpenZeppelin-compatible sorted-pair keccak Merkle tree.

Matches contracts/test/helpers/merkle.ts and OZ MerkleProof (commutative pair hashing).
"""

from __future__ import annotations

from dataclasses import dataclass

from eth_abi import encode
from eth_abi.packed import encode_packed
from eth_hash.auto import keccak
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address


def _norm_hex(h: str) -> str:
    h = h.lower()
    if not h.startswith("0x"):
        h = "0x" + h
    return h


def _hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(_norm_hex(h).removeprefix("0x"))


def hash_pair(a: str, b: str) -> str:
    """Sort by numeric value then keccak256(concat(left, right))."""
    a_n, b_n = _norm_hex(a), _norm_hex(b)
    left, right = (a_n, b_n) if int(a_n, 16) <= int(b_n, 16) else (b_n, a_n)
    digest = keccak(_hex_to_bytes(left) + _hex_to_bytes(right))
    return "0x" + digest.hex()


@dataclass(frozen=True)
class MerkleTree:
    root: str
    layers: tuple[tuple[str, ...], ...]
    leaves: tuple[str, ...]


def build_tree(leaves: list[str]) -> MerkleTree:
    if not leaves:
        raise ValueError("no leaves")
    layer: list[str] = [_norm_hex(x) for x in leaves]
    layers: list[tuple[str, ...]] = [tuple(layer)]
    while len(layer) > 1:
        nxt: list[str] = []
        for i in range(0, len(layer), 2):
            if i + 1 == len(layer):
                nxt.append(layer[i])
            else:
                nxt.append(hash_pair(layer[i], layer[i + 1]))
        layer = nxt
        layers.append(tuple(layer))
    return MerkleTree(root=layers[-1][0], layers=tuple(layers), leaves=tuple(layers[0]))


def get_proof(leaves: list[str], index: int) -> list[str]:
    tree = build_tree(leaves)
    proof: list[str] = []
    idx = index
    for layer in tree.layers[:-1]:
        pair_index = idx ^ 1
        if pair_index < len(layer):
            proof.append(layer[pair_index])
        idx //= 2
    return proof


def reputation_leaf(address: str, score_bp: int, evidence_count: int) -> str:
    """keccak256(abi.encodePacked(address, uint16 scoreBp, uint32 evidenceCount))."""
    addr: ChecksumAddress = to_checksum_address(address)
    packed = encode_packed(
        ["address", "uint16", "uint32"],
        [addr, int(score_bp), int(evidence_count)],
    )
    return "0x" + keccak(packed).hex()


def shortfall_leaf(interval_id: int, address: str, shortfall_wh: int) -> str:
    """keccak256(abi.encode(intervalId, participant, shortfallWh))."""
    addr: ChecksumAddress = to_checksum_address(address)
    encoded = encode(
        ["uint256", "address", "uint64"],
        [int(interval_id), addr, int(shortfall_wh)],
    )
    return "0x" + keccak(encoded).hex()


def verify_proof(leaf: str, proof: list[str], root: str) -> bool:
    """Verify unsorted proof against root using sorted-pair hashing."""
    computed = _norm_hex(leaf)
    for sibling in proof:
        computed = hash_pair(computed, sibling)
    return computed == _norm_hex(root)
