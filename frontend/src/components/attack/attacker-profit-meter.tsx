"use client";

import { cn } from "@/lib/utils";

export function AttackerProfitMeter({
  offPaise,
  onPaise,
}: {
  offPaise: number | null;
  onPaise: number | null;
}) {
  const max = Math.max(Math.abs(offPaise ?? 0), Math.abs(onPaise ?? 0), 1);
  const bar = (v: number | null, tone: "danger" | "success") => {
    if (v === null) return null;
    const pct = Math.min(100, (Math.abs(v) / max) * 100);
    return (
      <div className="flex items-center gap-2">
        <div className="h-2 flex-1 overflow-hidden rounded bg-surface-sunken">
          <div
            className={cn("h-full rounded", tone === "danger" ? "bg-danger" : "bg-success")}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="num w-28 text-right text-sm text-text">
          {v.toFixed(0)} <span className="text-text-muted">paise</span>
        </span>
      </div>
    );
  };

  return (
    <div className="space-y-2" aria-label="Attacker profit meter">
      <div>
        <div className="mb-0.5 text-xs text-text-muted">Defenses off — attacker-group gain</div>
        {bar(offPaise, "danger") ?? <p className="text-sm text-text-muted">Not run yet</p>}
      </div>
      <div>
        <div className="mb-0.5 text-xs text-text-muted">Defenses on — attacker-group gain</div>
        {bar(onPaise, "success") ?? <p className="text-sm text-text-muted">Not run yet</p>}
      </div>
    </div>
  );
}
