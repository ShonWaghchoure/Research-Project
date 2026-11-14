import { ethers } from "hardhat";

/** Sort-pair keccak Merkle tree (OpenZeppelin-compatible unsorted proof via sorted pairs). */
export function hashPair(a: string, b: string): string {
  const [left, right] = BigInt(a) <= BigInt(b) ? [a, b] : [b, a];
  return ethers.keccak256(ethers.concat([left, right]));
}

export function buildMerkleTree(leaves: string[]): { root: string; layers: string[][] } {
  if (leaves.length === 0) {
    throw new Error("no leaves");
  }
  const layers: string[][] = [leaves.map((x) => x.toLowerCase())];
  while (layers[layers.length - 1].length > 1) {
    const prev = layers[layers.length - 1];
    const next: string[] = [];
    for (let i = 0; i < prev.length; i += 2) {
      if (i + 1 === prev.length) {
        next.push(prev[i]);
      } else {
        next.push(hashPair(prev[i], prev[i + 1]));
      }
    }
    layers.push(next);
  }
  return { root: layers[layers.length - 1][0], layers };
}

export function getProof(leaves: string[], index: number): string[] {
  const { layers } = buildMerkleTree(leaves);
  const proof: string[] = [];
  let idx = index;
  for (let layer = 0; layer < layers.length - 1; layer++) {
    const nodes = layers[layer];
    const pairIndex = idx ^ 1;
    if (pairIndex < nodes.length) {
      proof.push(nodes[pairIndex]);
    }
    idx = Math.floor(idx / 2);
  }
  return proof;
}

/** OpenZeppelin MerkleProof expects unsorted proofs when using processProof (commutative via efficient hash).
 *  OZ v5 uses commutativeKeccak256 which sorts pairs — our hashPair matches that.
 */
export function reputationLeaf(participant: string, scoreBp: number, evidenceCount: number): string {
  return ethers.solidityPackedKeccak256(
    ["address", "uint16", "uint32"],
    [participant, scoreBp, evidenceCount]
  );
}

/** Leaf for one (seller, buyer) shortfall: keccak256(abi.encode(id, seller, buyer, shortfallWh)). */
export function shortfallLeaf(
  intervalId: number | bigint,
  seller: string,
  buyer: string,
  shortfallWh: number | bigint
): string {
  return ethers.keccak256(
    ethers.AbiCoder.defaultAbiCoder().encode(
      ["uint256", "address", "address", "uint64"],
      [intervalId, seller, buyer, shortfallWh]
    )
  );
}
