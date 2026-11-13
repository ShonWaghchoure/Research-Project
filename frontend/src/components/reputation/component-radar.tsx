"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { Reputation } from "@/lib/api/types";
import { useChartColors } from "@/lib/chart-theme";

const LABELS: { key: keyof Reputation["components"]; label: string }[] = [
  { key: "delivery", label: "Delivery" },
  { key: "reveal", label: "Reveal" },
  { key: "honesty", label: "Honesty" },
  { key: "collusion", label: "Collusion-free" },
];

/** Four-component reputation radar (delivery, reveal, honesty, collusion-free). */
export function ComponentRadar({ components }: { components: Reputation["components"] }) {
  const c = useChartColors();
  const data = LABELS.map(({ key, label }) => ({
    label,
    value: Math.max(0, Math.min(1, components[key])),
  }));

  return (
    <div className="h-[240px] w-full" role="img" aria-label="Reputation component radar">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke={c.border} />
          <PolarAngleAxis dataKey="label" tick={{ fill: c.text, fontSize: 11 }} />
          <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
          <Tooltip
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 4, fontSize: 12 }}
            formatter={(value) => {
              const n = typeof value === "number" ? value : Number(value);
              return [n.toFixed(2), "Component (0–1)"];
            }}
          />
          <Radar dataKey="value" stroke={c.accent} fill={c.accent} fillOpacity={0.25} isAnimationActive={false} />
        </RadarChart>
      </ResponsiveContainer>
      <ul className="mt-1 grid grid-cols-2 gap-1 text-xs">
        {LABELS.map(({ key, label }) => (
          <li key={key} className="flex justify-between rounded bg-surface-sunken px-2 py-1">
            <span className="text-text-muted">{label}</span>
            <span className="num text-text">{components[key].toFixed(2)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
