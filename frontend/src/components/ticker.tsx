"use client";

import { useEffect, useRef, useState } from "react";
import { useCurrentInterval } from "@/lib/queries";
import { formatSdr, paiseToInr } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Animates a number towards its target; respects reduced motion by jumping. */
export function useTweenedNumber(target: number | null, ms = 400): number | null {
  const [value, setValue] = useState<number | null>(target);
  const from = useRef<number | null>(target);
  useEffect(() => {
    if (target === null) return setValue(null);
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const start = from.current ?? target;
    if (reduce || start === target) {
      from.current = target;
      setValue(target);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / ms);
      const eased = 1 - Math.pow(1 - k, 3);
      setValue(start + (target - start) * eased);
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}

/** Live ticker: price, SDR, active participants. Price changes are announced politely. */
export function Ticker({ className }: { className?: string }) {
  const { data } = useCurrentInterval();
  const price = useTweenedNumber(data?.p_ref_paise ?? data?.prev_p_ref_paise ?? null);
  const items = [
    { label: "Reference price", value: price === null ? "—" : `₹${paiseToInr(Math.round(price))}`, unit: "per kWh", live: true },
    { label: "Supply ÷ demand", value: formatSdr(data?.sdr ?? null), unit: "SDR" },
    { label: "Active participants", value: data?.active_participants ?? "—", unit: "" },
    { label: "Interval", value: data ? `#${data.id}` : "—", unit: data?.state.toLowerCase() ?? "" },
  ];
  return (
    <dl className={cn("grid grid-cols-2 gap-px overflow-hidden rounded border border-border bg-border sm:grid-cols-4", className)}>
      {items.map((it) => (
        <div key={it.label} className="bg-surface-raised px-2 py-2">
          <dt className="text-xs text-text-muted">{it.label}</dt>
          <dd className="num mt-0.5 flex items-baseline gap-0.5 text-lg font-medium text-text" aria-live={it.live ? "polite" : undefined}>
            {it.value}
            {it.unit && <span className="text-xs font-normal text-text-muted">{it.unit}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
