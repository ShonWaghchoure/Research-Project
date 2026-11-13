"use client";

import { TIER_META } from "@/components/reputation-gauge";
import type { Tier } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ORDER: Tier[] = ["suspended", "probation", "standard", "trusted"];

/** Visual tier ladder with the rules for each step. */
export function TierLadder({ current }: { current?: Tier }) {
  return (
    <ol className="flex flex-col gap-1" aria-label="Reputation tier ladder">
      {ORDER.map((tier, i) => {
        const m = TIER_META[tier];
        const active = current === tier;
        return (
          <li
            key={tier}
            className={cn(
              "rounded border px-2 py-1.5",
              active ? "border-accent bg-accent-soft" : "border-border bg-surface-raised",
            )}
            aria-current={active ? "step" : undefined}
          >
            <div className="flex items-center gap-1 text-sm font-medium text-text">
              <span className="num text-text-faint">{i + 1}.</span>
              {m.icon}
              {m.label}
              {active && <span className="ml-auto text-xs font-normal text-accent">You are here</span>}
            </div>
            <p className="mt-0.5 text-xs text-text-muted">{m.rule}</p>
          </li>
        );
      })}
    </ol>
  );
}
