"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReputationHistoryPoint } from "@/lib/api/types";
import { useChartColors } from "@/lib/chart-theme";

export function ScoreHistoryChart({ history }: { history: ReputationHistoryPoint[] }) {
  const c = useChartColors();
  const rows = history.map((h) => ({
    label: `#${h.interval_id}`,
    score: h.score,
    evidence: h.evidence_count,
  }));

  return (
    <div className="h-[220px] w-full" role="img" aria-label="Reputation score history">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: c.faint, fontSize: 11 }} tickLine={false} axisLine={{ stroke: c.border }} minTickGap={28} />
          <YAxis domain={[0, 1]} tick={{ fill: c.faint, fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
          <Tooltip
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 4, fontSize: 12 }}
            formatter={(value) => {
              const n = typeof value === "number" ? value : Number(value);
              return [n.toFixed(3), "Score (0–1)"];
            }}
            labelFormatter={(label) => `Interval ${label}`}
          />
          <Line type="monotone" dataKey="score" stroke={c.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
