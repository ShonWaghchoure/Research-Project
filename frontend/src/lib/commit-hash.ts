import { encodeAbiParameters, keccak256, type Address, type Hex } from "viem";

export type Side = "buy" | "sell";

/** Side encoding used by Settlement.sol: 0 = buy, 1 = sell. */
export function sideCode(side: Side): 0 | 1 {
  return side === "buy" ? 0 : 1;
}

export interface CommitPreimage {
  intervalId: bigint | number;
  participant: Address;
  side: Side;
  qtyWh: bigint | number;
  limitPricePaise: number;
  /** Unix seconds; 0 when no deadline. */
  deadline: bigint | number;
  salt: Hex;
}

/**
 * Must equal Settlement.computeCommitHash:
 *   keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt))
 * with types (uint256, address, uint8, uint64, uint32, uint64, bytes32).
 */
export function computeCommitHash(p: CommitPreimage): Hex {
  return keccak256(
    encodeAbiParameters(
      [
        { type: "uint256" },
        { type: "address" },
        { type: "uint8" },
        { type: "uint64" },
        { type: "uint32" },
        { type: "uint64" },
        { type: "bytes32" },
      ],
      [
        BigInt(p.intervalId),
        p.participant,
        sideCode(p.side),
        BigInt(p.qtyWh),
        p.limitPricePaise,
        BigInt(p.deadline),
        p.salt,
      ],
    ),
  );
}

/** 32 random bytes from the browser CSPRNG. */
export function randomSalt(): Hex {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return `0x${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}` as Hex;
}
