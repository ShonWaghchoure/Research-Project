import { describe, expect, it } from "vitest";
import { participantSchema, positionSchema } from "./schemas";

describe("participantSchema (mirrors backend validation)", () => {
  const base = { type: "prosumer", display_name: "", feeder_node_id: "n4", pv_capacity_kw: 3, battery_kwh: 5, ev_v2g: false };

  it("accepts a prosumer", () => {
    expect(participantSchema.safeParse(base).success).toBe(true);
  });
  it("rejects a consumer with PV", () => {
    const r = participantSchema.safeParse({ ...base, type: "consumer" });
    expect(r.success).toBe(false);
  });
  it("requires EV fields for an EV", () => {
    const r = participantSchema.safeParse({ ...base, type: "ev" });
    expect(r.success).toBe(false);
    expect(participantSchema.safeParse({ ...base, type: "ev", ev_battery_kwh: 60, ev_max_power_kw: 7 }).success).toBe(true);
  });
});

describe("positionSchema", () => {
  it("keeps the limit inside the tariff band", () => {
    expect(positionSchema.safeParse({ side: "buy", qty_kwh: 1, limit_price_inr: 2.99 }).success).toBe(false);
    expect(positionSchema.safeParse({ side: "buy", qty_kwh: 1, limit_price_inr: 8.01 }).success).toBe(false);
    expect(positionSchema.safeParse({ side: "sell", qty_kwh: 1, limit_price_inr: 3 }).success).toBe(true);
  });
  it("rejects zero and sub-Wh quantities", () => {
    expect(positionSchema.safeParse({ side: "buy", qty_kwh: 0, limit_price_inr: 5 }).success).toBe(false);
    expect(positionSchema.safeParse({ side: "buy", qty_kwh: 1.0005, limit_price_inr: 5 }).success).toBe(false);
  });
});
