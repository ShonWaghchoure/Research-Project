/**
 * Client-side mirror of backend/app/engine/pricing.py, used only to show the
 * expected price range before a position is committed. The backend remains the
 * source of truth; these numbers are a preview and are labelled as such.
 *
 * Worked values (Phase 1): SDR 0.25 → 7.71, 0.5 → 7.00, 1 → 5.50, 2 → 4.00, 4 → 3.29
 */
export interface PricingParams {
  pFitPaise: number;
  pRetPaise: number;
  k: number;
  alpha: number;
}

export const DEFAULT_PRICING: PricingParams = {
  pFitPaise: 300,
  pRetPaise: 800,
  k: 2,
  alpha: 0.7,
};

export function sdr(supplyWh: number, demandWh: number): number {
  if (demandWh <= 0) return supplyWh > 0 ? Number.POSITIVE_INFINITY : 1;
  return supplyWh / demandWh;
}

/** Raw SDR price in paise, before smoothing. */
export function priceFromSdr(s: number, p: PricingParams = DEFAULT_PRICING): number {
  if (!Number.isFinite(s)) return p.pFitPaise;
  const raw = p.pFitPaise + (p.pRetPaise - p.pFitPaise) / (1 + Math.pow(s, p.k));
  return Math.min(p.pRetPaise, Math.max(p.pFitPaise, raw));
}

/** Smoothed reference price in paise, rounded like the engine. */
export function referencePrice(
  s: number,
  prevPRefPaise: number | null,
  p: PricingParams = DEFAULT_PRICING,
): number {
  const raw = priceFromSdr(s, p);
  const smoothed = prevPRefPaise === null ? raw : p.alpha * raw + (1 - p.alpha) * prevPRefPaise;
  return Math.round(Math.min(p.pRetPaise, Math.max(p.pFitPaise, smoothed)));
}

export interface ExpectedRange {
  lowPaise: number;
  highPaise: number;
  sdrWithout: number;
  sdrWith: number;
}

/**
 * Expected clearing price range if the user adds `qtyWh` on `side` to the
 * current anonymised order book.
 */
export function expectedPriceRange(
  side: "buy" | "sell",
  qtyWh: number,
  supplyWh: number,
  demandWh: number,
  prevPRefPaise: number | null,
  p: PricingParams = DEFAULT_PRICING,
): ExpectedRange {
  const sWithout = sdr(supplyWh, demandWh);
  const sWith =
    side === "buy" ? sdr(supplyWh, demandWh + qtyWh) : sdr(supplyWh + qtyWh, demandWh);
  const a = referencePrice(sWithout, prevPRefPaise, p);
  const b = referencePrice(sWith, prevPRefPaise, p);
  return {
    lowPaise: Math.min(a, b),
    highPaise: Math.max(a, b),
    sdrWithout: sWithout,
    sdrWith: sWith,
  };
}
