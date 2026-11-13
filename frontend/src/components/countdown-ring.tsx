"use client";

import { useEffect, useState } from "react";
import { formatCountdown } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Ring that drains from `startsAt` to `endsAt`. Time left is also shown as text and
 * announced each 30 s, so the ring itself is decorative.
 */
export function CountdownRing({
  startsAt,
  endsAt,
  label,
  size = 120,
  className,
}: {
  startsAt: string;
  endsAt: string;
  label: string;
  size?: number;
  className?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const start = new Date(startsAt).getTime();
  const end = new Date(endsAt).getTime();
  const total = Math.max(1, end - start);
  const remaining = Math.max(0, end - now);
  const fraction = Math.min(1, Math.max(0, remaining / total));

  const stroke = 6;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const seconds = Math.ceil(remaining / 1000);

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeLinecap="butt"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - fraction)}
          style={{ transition: "stroke-dashoffset 1s linear" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-xl font-medium text-text" aria-hidden>
          {formatCountdown(seconds)}
        </span>
        <span className="text-xs text-text-muted">{label}</span>
        <span className="sr-only" aria-live={seconds % 30 === 0 ? "polite" : "off"}>
          {label}: {formatCountdown(seconds)} remaining
        </span>
      </div>
    </div>
  );
}
