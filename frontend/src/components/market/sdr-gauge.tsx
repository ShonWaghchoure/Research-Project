"use client";

import { InfoTip } from "@/components/ui/tooltip";
import { formatSdr } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Supply ÷ demand gauge. SDR = 1 is balance; above 1 is surplus (price falls toward feed-in);
 * below 1 is scarce (price rises toward retail).
 */
export function SdrGauge({ sdr, className }: { sdr: number | null | undefined; className?: string }) {
  const value = sdr === null || sdr === undefined || !Number.isFinite(sdr) ? null : Math.min(4, Math.max(0, sdr));
  // Map 0..4 onto a half-ring arc (π..0).
  const score = value === null ? 0 : value / 4;
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
  const balance = 0.25; // SDR = 1 on a 0..4 scale

  return (
    <div className={cn("flex flex-col items-center", className)}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        <path d={arc(0, 1)} fill="none" stroke="var(--border)" strokeWidth={10} />
        <path d={arc(0, score)} fill="none" stroke="var(--accent)" strokeWidth={10} />
        {/* Balance mark at SDR = 1 */}
        <line
          x1={cx + (r - 8) * Math.cos(Math.PI * (1 - balance))}
          y1={cy - (r - 8) * Math.sin(Math.PI * (1 - balance))}
          x2={cx + (r + 8) * Math.cos(Math.PI * (1 - balance))}
          y2={cy - (r + 8) * Math.sin(Math.PI * (1 - balance))}
          stroke="var(--text-faint)"
          strokeWidth={1.5}
        />
        <text x={cx} y={cy - 18} textAnchor="middle" className="num" fill="var(--text)" fontSize={28} fontWeight={500}>
          {formatSdr(sdr)}
        </text>
        <text x={cx} y={cy} textAnchor="middle" fill="var(--text-muted)" fontSize={11}>
          supply ÷ demand
        </text>
      </svg>
      <div className="flex items-center gap-1 text-xs text-text-muted">
        <span>{value !== null && value < 1 ? "Scarce" : value !== null && value > 1 ? "Surplus" : "Balanced"}</span>
        <InfoTip label="How SDR sets the price">
          <p>
            SDR is reputation-weighted supply divided by demand. The raw price is
            p_fit + (p_ret − p_fit) / (1 + SDR²), then smoothed toward the previous interval.
            A median quantity cap and reputation weights limit manipulation.
          </p>
        </InfoTip>
      </div>
      <div className="sr-only">
        Supply to demand ratio {formatSdr(sdr)}. Values above one mean surplus and a lower clearing price.
      </div>
    </div>
  );
}
