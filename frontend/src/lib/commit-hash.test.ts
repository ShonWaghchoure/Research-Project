import { describe, expect, it } from "vitest";
import { computeCommitHash, randomSalt, sideCode } from "./commit-hash";

/**
 * Expected values computed independently with Python eth_abi + keccak (the backend's
 * stack), using the same abi.encode layout as Settlement.computeCommitHash.
 * If these ever differ, every reveal fails and every participant is penalised.
 */
describe("computeCommitHash", () => {
  it("matches eth_abi for a sell with no deadline", () => {
    expect(
      computeCommitHash({
        intervalId: 42,
        participant: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        side: "sell",
        qtyWh: 1500,
        limitPricePaise: 550,
        deadline: 0,
        salt: `0x${"11".repeat(32)}`,
      }),
    ).toBe("0x97c50275ec5b34514d97e3f43b66fbd3f060abe997ad4f6b71665bde18d9825f");
  });

  it("matches eth_abi for a buy with a deadline", () => {
    expect(
      computeCommitHash({
        intervalId: 7n,
        participant: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        side: "buy",
        qtyWh: 250n,
        limitPricePaise: 800,
        deadline: 1767225600n,
        salt: `0x${"ab".repeat(32)}`,
      }),
    ).toBe("0x0928fc187dfa98240943364acd4897d083da2d8fe096b362713434610313133e");
  });

  it("changes when any field changes", () => {
    const base = {
      intervalId: 1,
      participant: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8" as const,
      side: "buy" as const,
      qtyWh: 1000,
      limitPricePaise: 500,
      deadline: 0,
      salt: `0x${"00".repeat(31)}01` as const,
    };
    const h = computeCommitHash(base);
    expect(computeCommitHash({ ...base, side: "sell" })).not.toBe(h);
    expect(computeCommitHash({ ...base, qtyWh: 1001 })).not.toBe(h);
    expect(computeCommitHash({ ...base, limitPricePaise: 501 })).not.toBe(h);
    expect(computeCommitHash({ ...base, intervalId: 2 })).not.toBe(h);
  });

  it("encodes sides as 0 = buy, 1 = sell", () => {
    expect(sideCode("buy")).toBe(0);
    expect(sideCode("sell")).toBe(1);
  });

  it("generates distinct 32-byte salts", () => {
    const a = randomSalt();
    const b = randomSalt();
    expect(a).toMatch(/^0x[0-9a-f]{64}$/);
    expect(a).not.toBe(b);
  });
});
