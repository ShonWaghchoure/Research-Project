import { describe, expect, it } from "vitest";
import { expectedPriceRange, priceFromSdr, referencePrice } from "./pricing";

describe("SDR pricing mirror", () => {
  // Phase 1 worked values (₹/kWh): 0.25 → 7.71, 0.5 → 7.00, 1 → 5.50, 2 → 4.00, 4 → 3.29
  it.each([
    [0.25, 770.6],
    [0.5, 700],
    [1, 550],
    [2, 400],
    [4, 329.4],
  ])("SDR %f gives about %f paise", (s, expected) => {
    expect(priceFromSdr(s)).toBeCloseTo(expected, 0);
  });

  it("stays inside the feed-in and retail band", () => {
    for (const s of [0, 0.001, 1, 1000, Infinity]) {
      const p = priceFromSdr(s);
      expect(p).toBeGreaterThanOrEqual(300);
      expect(p).toBeLessThanOrEqual(800);
    }
  });

  it("smooths towards the previous reference price", () => {
    // raw 550, prev 800 → 0.7*550 + 0.3*800 = 625
    expect(referencePrice(1, 800)).toBe(625);
    expect(referencePrice(1, null)).toBe(550);
  });

  it("a buy raises the expected price, a sell lowers it", () => {
    const buy = expectedPriceRange("buy", 5000, 10000, 10000, null);
    const sell = expectedPriceRange("sell", 5000, 10000, 10000, null);
    expect(buy.highPaise).toBeGreaterThan(550);
    expect(sell.lowPaise).toBeLessThan(550);
    expect(buy.lowPaise).toBeLessThanOrEqual(buy.highPaise);
  });
});
