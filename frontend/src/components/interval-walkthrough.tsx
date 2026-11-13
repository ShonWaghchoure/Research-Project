"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "commit", title: "Commit", text: "Each participant submits one sealed net position: buy or sell, kWh, limit price. Only its hash goes on chain." },
  { key: "reveal", title: "Reveal", text: "Positions are revealed and checked against the hash. A missed reveal counts against reputation." },
  { key: "price", title: "Price", text: "A single reference price is set from the supply-to-demand ratio, bounded by the feed-in and retail tariffs." },
  { key: "match", title: "Match", text: "A grid-aware optimisation matches buyers and sellers, ordering by reputation and respecting line limits." },
  { key: "settle", title: "Settle", text: "Trades are posted on chain and escrow moves. The grid covers anything left unmatched." },
  { key: "meter", title: "Meter", text: "Signed meter readings verify delivery. Shortfalls are compensated and reputation is updated and anchored." },
];

/** Six-step walk-through of one interval; auto-advances, pauses on hover/focus, keyboard selectable. */
export function IntervalWalkthrough({ className }: { className?: string }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setI((x) => (x + 1) % STEPS.length), 3200);
    return () => clearInterval(t);
  }, [paused]);

  return (
    <div
      className={cn("rounded border border-border bg-surface-raised", className)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div role="tablist" aria-label="Steps of one market interval" className="grid grid-cols-3 border-b border-border sm:grid-cols-6">
        {STEPS.map((s, idx) => (
          <button
            key={s.key}
            role="tab"
            aria-selected={idx === i}
            aria-controls={`walk-${s.key}`}
            id={`tab-${s.key}`}
            onClick={() => setI(idx)}
            className={cn(
              "relative px-1 py-1 text-xs font-medium transition-colors",
              idx === i ? "text-text" : "text-text-muted hover:text-text",
            )}
          >
            {idx + 1}. {s.title}
            {idx === i && (
              <motion.span
                layoutId="walk-underline"
                aria-hidden
                transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 40 }}
                className="absolute inset-x-0 -bottom-px h-[2px] bg-accent"
              />
            )}
          </button>
        ))}
      </div>
      <div className="relative min-h-[88px] px-3 py-2">
        {STEPS.map((s, idx) => (
          <motion.p
            key={s.key}
            role="tabpanel"
            id={`walk-${s.key}`}
            aria-labelledby={`tab-${s.key}`}
            hidden={idx !== i}
            initial={false}
            animate={{ opacity: idx === i ? 1 : 0 }}
            transition={{ duration: reduce ? 0 : 0.25 }}
            className="text-sm text-text-muted"
          >
            <span className="font-medium text-text">{s.title}. </span>
            {s.text}
          </motion.p>
        ))}
        <div className="mt-2 h-px w-full bg-border" aria-hidden>
          <motion.div
            className="h-px bg-accent"
            key={`${i}-${paused}`}
            initial={{ width: "0%" }}
            animate={{ width: paused ? "0%" : "100%" }}
            transition={{ duration: reduce || paused ? 0 : 3.2, ease: "linear" }}
          />
        </div>
      </div>
    </div>
  );
}
