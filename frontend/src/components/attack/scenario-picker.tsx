"use client";

import type { AttackScenario } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const SCENARIOS: { id: AttackScenario; label: string; blurb: string }[] = [
  {
    id: "sybil_farm",
    label: "Sybil farm",
    blurb: "One large seller plus many tiny low-reputation identities bidding at the ceiling.",
  },
  {
    id: "collusion_ring",
    label: "Collusion ring",
    blurb: "A fixed ring wash-trades among itself to farm reputation.",
  },
  {
    id: "price_manipulation",
    label: "Price manipulation",
    blurb: "A large seller withholds supply to push the SDR price up.",
  },
  {
    id: "false_reports",
    label: "False reports",
    blurb: "Prosumers inflate reported PV output and claim full delivery.",
  },
  {
    id: "defect_after_trust",
    label: "Defect after trust",
    blurb: "Participants behave honestly for a while, then stop delivering.",
  },
];

export function ScenarioPicker({
  value,
  onChange,
}: {
  value: AttackScenario;
  onChange: (s: AttackScenario) => void;
}) {
  return (
    <div role="radiogroup" aria-label="Attack scenario" className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
      {SCENARIOS.map((s) => {
        const active = s.id === value;
        return (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(s.id)}
            className={cn(
              "rounded border px-2 py-2 text-left transition-colors",
              active
                ? "border-accent bg-accent-soft text-text"
                : "border-border bg-surface-raised text-text-muted hover:border-border-strong hover:text-text",
            )}
          >
            <div className="text-sm font-medium text-text">{s.label}</div>
            <p className="mt-0.5 text-xs text-text-muted">{s.blurb}</p>
          </button>
        );
      })}
    </div>
  );
}
