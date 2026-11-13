"use client";

import { useMemo, useState } from "react";
import type { Reputation } from "@/lib/api/types";

/**
 * Approximate perfect-interval path to Trusted using the same Beta prior as the engine
 * (alpha0=1, beta0=2, kappa=3, no forgetting for the forecast).
 */
export function intervalsToTrusted(
  alpha: number,
  beta: number,
  evidence: number,
  deliveryRate = 1,
): number {
  if (evidence >= 100) {
    const n = alpha + beta;
    const mu = alpha / n;
    const sd = Math.sqrt((alpha * beta) / (n * n * (n + 1)));
    if (mu - sd >= 0.8) return 0;
  }
  let a = alpha;
  let b = beta;
  let e = evidence;
  const s = Math.max(0, Math.min(1, deliveryRate));
  for (let i = 0; i < 500; i++) {
    a += s;
    b += 3 * (1 - s);
    e += 1;
    const n = a + b;
    const mu = a / n;
    const sd = Math.sqrt((a * b) / (n * n * (n + 1)));
    const R = Math.max(0, mu - sd);
    if (R >= 0.8 && e >= 100) return i + 1;
  }
  return 500;
}

/** Interactive what-if: how many intervals to Trusted at a chosen delivery rate. */
export function WhatIfPanel({ reputation }: { reputation: Reputation }) {
  const [rate, setRate] = useState(1);
  // Back out approximate alpha/beta from score + evidence for the forecast.
  const { alpha, beta } = useMemo(() => {
    const e = Math.max(0, reputation.evidence_count);
    // Prior (1,2) plus e perfect-ish updates approximating current score.
    const target = Math.max(0.05, Math.min(0.95, reputation.score));
    // Solve roughly: mu ≈ alpha/(alpha+beta) ≈ target with prior weight.
    const alpha = 1 + e * target;
    const beta = 2 + e * (1 - target) * 3 * 0.2;
    return { alpha, beta };
  }, [reputation.evidence_count, reputation.score]);

  const n = intervalsToTrusted(alpha, beta, reputation.evidence_count, rate);
  const apiHint = reputation.intervals_to_trusted;

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-text-muted">Assumed delivery quality each interval</span>
        <input
          type="range"
          min={0.5}
          max={1}
          step={0.05}
          value={rate}
          onChange={(e) => setRate(Number(e.target.value))}
          aria-valuetext={`${Math.round(rate * 100)} percent`}
        />
        <span className="num text-xs text-text">{Math.round(rate * 100)}%</span>
      </label>
      <p className="text-sm text-text">
        About{" "}
        <span className="num text-lg font-medium text-accent">{n === 500 ? "500+" : n}</span>{" "}
        perfect{rate < 1 ? "-rate" : ""} intervals to reach Trusted
        {reputation.tier === "trusted" ? " (already Trusted)" : ""}.
      </p>
      {apiHint !== null && rate === 1 && (
        <p className="text-xs text-text-muted">
          Server estimate at full delivery: <span className="num text-text">{apiHint}</span> intervals.
        </p>
      )}
      <p className="text-xs text-text-muted">
        Trusted needs score ≥ 0.80 and at least 100 pieces of evidence. Failures cost about 3× a success.
      </p>
    </div>
  );
}
