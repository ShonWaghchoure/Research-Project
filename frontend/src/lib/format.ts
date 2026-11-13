/**
 * Formatting helpers.
 * Rule 2 of the project: money is integer paise and energy is integer Wh at every
 * boundary. These helpers only convert for display; they never feed values back.
 */

const inr = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const kwh = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 3,
});

const pct = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

/** 550 paise → "5.50" (per kWh). */
export function paiseToInr(paise: number | bigint | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  return inr.format(Number(paise) / 100);
}

/** 550 → "₹5.50 / kWh". Always labelled with its unit. */
export function formatPrice(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  return `₹${paiseToInr(paise)} / kWh`;
}

/** Total money in paise → "₹1,234.56". */
export function formatInr(paise: number | bigint | null | undefined): string {
  if (paise === null || paise === undefined) return "—";
  return `₹${paiseToInr(paise)}`;
}

/** 1500 Wh → "1.5 kWh". */
export function formatKwh(wh: number | null | undefined, unit = true): string {
  if (wh === null || wh === undefined) return "—";
  const v = kwh.format(wh / 1000);
  return unit ? `${v} kWh` : v;
}

/** 3.5 → "3.5 kW". */
export function formatKw(kw: number | null | undefined): string {
  if (kw === null || kw === undefined) return "—";
  return `${kwh.format(kw)} kW`;
}

export function formatPct(value: number | null | undefined, fractionOf1 = true): string {
  if (value === null || value === undefined) return "—";
  return `${pct.format(fractionOf1 ? value * 100 : value)}%`;
}

export function formatSdr(sdr: number | null | undefined): string {
  if (sdr === null || sdr === undefined) return "—";
  return sdr.toFixed(2);
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

/** Form input in kWh (string) → integer Wh, or null when invalid. */
export function kwhToWh(input: string | number): number | null {
  const n = typeof input === "number" ? input : Number(input);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 1000);
}

/** Form input in ₹/kWh (string) → integer paise, or null when invalid. */
export function inrToPaise(input: string | number): number | null {
  const n = typeof input === "number" ? input : Number(input);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

/** Payment for qty at price, same floor as Settlement._payment. */
export function paymentPaise(qtyWh: number, pricePaise: number): number {
  return Math.floor((qtyWh * pricePaise) / 1000);
}
