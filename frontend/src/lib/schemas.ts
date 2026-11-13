import { z } from "zod";

/** Mirrors backend/app/schemas/participants.py so errors appear before the request. */
export const participantSchema = z
  .object({
    type: z.enum(["consumer", "prosumer", "ev"]),
    display_name: z.string().trim().max(120, "At most 120 characters").optional().or(z.literal("")),
    feeder_node_id: z.string().trim().min(1, "Choose a feeder node").max(32),
    pv_capacity_kw: z.coerce.number().min(0, "Cannot be negative").max(1000, "At most 1000 kW"),
    battery_kwh: z.coerce.number().min(0, "Cannot be negative").max(5000, "At most 5000 kWh"),
    ev_battery_kwh: z.coerce.number().min(0).max(500, "At most 500 kWh").optional(),
    ev_max_power_kw: z.coerce.number().min(0).max(500, "At most 500 kW").optional(),
    ev_v2g: z.boolean().default(false),
  })
  .superRefine((v, ctx) => {
    if (v.type === "ev") {
      if (v.ev_battery_kwh === undefined || Number.isNaN(v.ev_battery_kwh) || v.ev_battery_kwh <= 0)
        ctx.addIssue({ code: "custom", path: ["ev_battery_kwh"], message: "Required for an EV" });
      if (v.ev_max_power_kw === undefined || Number.isNaN(v.ev_max_power_kw) || v.ev_max_power_kw <= 0)
        ctx.addIssue({ code: "custom", path: ["ev_max_power_kw"], message: "Required for an EV" });
    }
    if (v.type === "consumer" && v.pv_capacity_kw > 0)
      ctx.addIssue({ code: "custom", path: ["pv_capacity_kw"], message: "A consumer has no PV. Choose prosumer instead." });
  });

export type ParticipantForm = z.output<typeof participantSchema>;
export type ParticipantFormInput = z.input<typeof participantSchema>;

export const P_FIT_INR = 3;
export const P_RET_INR = 8;

export const positionSchema = z.object({
  side: z.enum(["buy", "sell"]),
  qty_kwh: z.coerce
    .number({ error: "Enter a quantity" })
    .positive("Quantity must be above 0")
    .max(1000, "At most 1000 kWh per interval")
    .refine((v) => Math.round(v * 1000) === v * 1000 || Math.abs(Math.round(v * 1000) - v * 1000) < 1e-9, "Use at most 3 decimals (1 Wh)"),
  limit_price_inr: z.coerce
    .number({ error: "Enter a price" })
    .min(P_FIT_INR, `At least ₹${P_FIT_INR.toFixed(2)} (feed-in tariff)`)
    .max(P_RET_INR, `At most ₹${P_RET_INR.toFixed(2)} (retail tariff)`),
  /** Local datetime string from <input type="datetime-local">, optional. */
  deadline: z.string().optional().or(z.literal("")),
});

export type PositionForm = z.output<typeof positionSchema>;
export type PositionFormInput = z.input<typeof positionSchema>;

export const amountSchema = z.object({
  amount_inr: z.coerce.number({ error: "Enter an amount" }).positive("Must be above 0"),
});
export type AmountForm = z.output<typeof amountSchema>;
export type AmountFormInput = z.input<typeof amountSchema>;
