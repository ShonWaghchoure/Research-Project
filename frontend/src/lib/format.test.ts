import { describe, expect, it } from "vitest";
import { formatCountdown, formatKwh, formatPrice, inrToPaise, kwhToWh, paymentPaise } from "./format";
import { readableTxError } from "./tx";

describe("format", () => {
  it("labels units", () => {
    expect(formatPrice(550)).toBe("₹5.50 / kWh");
    expect(formatKwh(1500)).toBe("1.5 kWh");
    expect(formatPrice(null)).toBe("—");
  });

  it("converts inputs to integers at the boundary", () => {
    expect(kwhToWh("1.234")).toBe(1234);
    expect(inrToPaise("5.505")).toBe(551);
    expect(kwhToWh("-1")).toBeNull();
    expect(inrToPaise("abc")).toBeNull();
  });

  it("floors payment like Settlement._payment", () => {
    expect(paymentPaise(1500, 550)).toBe(825);
    expect(paymentPaise(1, 550)).toBe(0);
  });

  it("formats countdowns", () => {
    expect(formatCountdown(65)).toBe("1:05");
    expect(formatCountdown(-3)).toBe("0:00");
  });
});

describe("readableTxError", () => {
  it("maps known contract reverts to plain sentences", () => {
    expect(readableTxError(new Error("execution reverted: Settlement: commit closed"))).toMatch(/commit window/i);
    expect(readableTxError(new Error("MockINR: already claimed today"))).toMatch(/already used the faucet/i);
  });
  it("strips contract prefixes from unknown reasons", () => {
    expect(readableTxError(new Error("Registry: something new"))).toBe("something new");
  });
});
