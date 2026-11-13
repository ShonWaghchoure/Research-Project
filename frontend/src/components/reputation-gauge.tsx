import { ShieldAlert, ShieldCheck, ShieldQuestion, ShieldX } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InfoTip } from "@/components/ui/tooltip";
import type { Reputation, Tier } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const TIER_META: Record<Tier, { label: string; tone: "danger" | "warning" | "neutral" | "success"; icon: React.ReactNode; rule: string }> = {
  suspended: {
    label: "Suspended",
    tone: "danger",
    icon: <ShieldX className="h-[12px] w-[12px]" aria-hidden />,
    rule: "Score below 0.15 with evidence of failures, or a high-severity flag. Cannot trade.",
  },
  probation: {
    label: "Probation",
    tone: "warning",
    icon: <ShieldQuestion className="h-[12px] w-[12px]" aria-hidden />,
    rule: "Fewer than 20 pieces of evidence, or score below 0.30. Can trade with a reduced volume cap.",
  },
  standard: {
    label: "Standard",
    tone: "neutral",
    icon: <ShieldAlert className="h-[12px] w-[12px]" aria-hidden />,
    rule: "Score between 0.30 and 0.80.",
  },
  trusted: {
    label: "Trusted",
    tone: "success",
    icon: <ShieldCheck className="h-[12px] w-[12px]" aria-hidden />,
    rule: "Score of 0.80 or more with at least 100 pieces of evidence. Matched first.",
  },
};

export function TierBadge({ tier, className }: { tier: Tier; className?: string }) {
  const m = TIER_META[tier];
  return (
    <Badge tone={m.tone} icon={m.icon} className={className}>
      {m.label}
    </Badge>
  );
}

/**
 * Half-ring gauge for the Beta reputation score in [0, 1], with tier thresholds marked.
 * The number and tier are always shown as text.
 */
export function ReputationGauge({ reputation, className }: { reputation: Reputation; className?: string }) {
  const score = Math.min(1, Math.max(0, reputation.score));
  const w = 200;
  const h = 110;
  const r = 86;
  const cx = w / 2;
  const cy = 100;
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from);
    const a1 = Math.PI * (1 - to);
    const x0 = cx + r * Math.cos(a0);
    const y0 = cy - r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1);
    const y1 = cy - r * Math.sin(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 ${to - from > 0.5 ? 1 : 0} 1 ${x1} ${y1}`;
  };

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        <path d={arc(0, 1)} fill="none" stroke="var(--border)" strokeWidth={10} />
        <path d={arc(0, score)} fill="none" stroke="var(--accent)" strokeWidth={10} style={{ transition: "d 400ms ease" }} />
        {[0.15, 0.3, 0.8].map((t) => {
          const a = Math.PI * (1 - t);
          return (
            <line
              key={t}
              x1={cx + (r - 8) * Math.cos(a)}
              y1={cy - (r - 8) * Math.sin(a)}
              x2={cx + (r + 8) * Math.cos(a)}
              y2={cy - (r + 8) * Math.sin(a)}
              stroke="var(--text-faint)"
              strokeWidth={1}
            />
          );
        })}
        <text x={cx} y={cy - 18} textAnchor="middle" className="num" fill="var(--text)" fontSize={28} fontWeight={500}>
          {score.toFixed(2)}
        </text>
        <text x={cx} y={cy} textAnchor="middle" fill="var(--text-muted)" fontSize={11}>
          reputation score (0 to 1)
        </text>
      </svg>
      <div className="sr-only">Reputation score {score.toFixed(2)} out of 1, tier {TIER_META[reputation.tier].label}.</div>
      <div className="flex items-center gap-1">
        <TierBadge tier={reputation.tier} />
        <InfoTip label="How tiers work">
          <ul className="flex flex-col gap-0.5">
            {(Object.keys(TIER_META) as Tier[]).map((t) => (
              <li key={t}>
                <span className="font-medium">{TIER_META[t].label}:</span> {TIER_META[t].rule}
              </li>
            ))}
            <li className="text-text-muted">
              Reputation decides who is matched and in what order. It never changes the price.
            </li>
          </ul>
        </InfoTip>
      </div>
      {reputation.intervals_to_trusted !== null && reputation.tier !== "trusted" && (
        <p className="mt-1 text-xs text-text-muted">
          About <span className="num font-medium text-text">{reputation.intervals_to_trusted}</span> perfect intervals to reach Trusted.
        </p>
      )}
    </div>
  );
}
