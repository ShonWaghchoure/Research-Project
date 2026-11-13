"use client";

import { Stat } from "@/components/ui/card";
import { InfoTip } from "@/components/ui/tooltip";
import type { FairnessMetric } from "@/lib/api/types";

const METRICS: {
  key: keyof Pick<
    FairnessMetric,
    "jain" | "gini" | "hhi" | "small_actor_parity" | "price_impact" | "welfare_efficiency"
  >;
  label: string;
  hint: string;
  format: (v: number) => string;
}[] = [
  {
    key: "jain",
    label: "Jain index",
    hint: "1 = equal matched shares; lower means concentration of matching.",
    format: (v) => v.toFixed(3),
  },
  {
    key: "gini",
    label: "Gini of gains",
    hint: "0 = equal welfare gains vs grid-only; higher is more unequal.",
    format: (v) => v.toFixed(3),
  },
  {
    key: "hhi",
    label: "HHI (sellers)",
    hint: "Sum of squared seller volume shares. Lower is less concentrated.",
    format: (v) => v.toFixed(3),
  },
  {
    key: "small_actor_parity",
    label: "Small-actor parity",
    hint: "Matched share of the smallest 50% ÷ their offered share. 1 is proportional.",
    format: (v) => v.toFixed(3),
  },
  {
    key: "price_impact",
    label: "Price impact",
    hint: "Typical change in raw price (as a fraction of the tariff band) from one actor’s quantity.",
    format: (v) => v.toFixed(4),
  },
  {
    key: "welfare_efficiency",
    label: "Welfare efficiency",
    hint: "Matched welfare ÷ unconstrained optimum. Grid limits and reputation gates can lower this.",
    format: (v) => v.toFixed(3),
  },
];

export function MetricCards({ latest }: { latest: FairnessMetric | null }) {
  return (
    <div className="grid grid-cols-2 gap-1 md:grid-cols-3">
      {METRICS.map((m) => (
        <Stat
          key={m.key}
          label={m.label}
          value={latest ? m.format(latest[m.key]) : "—"}
          hint={
            <span className="inline-flex items-center gap-0.5">
              Interval {latest ? `#${latest.interval_id}` : "—"}
              <InfoTip label={`About ${m.label}`}>{m.hint}</InfoTip>
            </span>
          }
        />
      ))}
    </div>
  );
}

export { METRICS as FAIRNESS_METRIC_DEFS };
