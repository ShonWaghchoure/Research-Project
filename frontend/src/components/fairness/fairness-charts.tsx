"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FairnessMetric } from "@/lib/api/types";
import { useChartColors } from "@/lib/chart-theme";
import { FAIRNESS_METRIC_DEFS } from "./metric-cards";

/** Overlay B2 vs B3 time series for the six fairness metrics. */
export function FairnessCharts({
  b2,
  b3,
}: {
  b2: FairnessMetric[];
  b3: FairnessMetric[];
}) {
  const c = useChartColors();
  type ChartRow = {
    label: string;
    interval_id: number;
    jain_b2?: number;
    gini_b2?: number;
    hhi_b2?: number;
    small_actor_parity_b2?: number;
    price_impact_b2?: number;
    welfare_efficiency_b2?: number;
    jain_b3?: number;
    gini_b3?: number;
    hhi_b3?: number;
    small_actor_parity_b3?: number;
    price_impact_b3?: number;
    welfare_efficiency_b3?: number;
  };
  const byId = new Map<number, ChartRow>();
  for (const row of b3) {
    byId.set(row.interval_id, {
      label: `#${row.interval_id}`,
      interval_id: row.interval_id,
      jain_b3: row.jain,
      gini_b3: row.gini,
      hhi_b3: row.hhi,
      small_actor_parity_b3: row.small_actor_parity,
      price_impact_b3: row.price_impact,
      welfare_efficiency_b3: row.welfare_efficiency,
    });
  }
  for (const row of b2) {
    const existing = byId.get(row.interval_id) ?? {
      label: `#${row.interval_id}`,
      interval_id: row.interval_id,
    };
    byId.set(row.interval_id, {
      ...existing,
      jain_b2: row.jain,
      gini_b2: row.gini,
      hhi_b2: row.hhi,
      small_actor_parity_b2: row.small_actor_parity,
      price_impact_b2: row.price_impact,
      welfare_efficiency_b2: row.welfare_efficiency,
    });
  }
  const rows = [...byId.values()].sort((a, b) => a.interval_id - b.interval_id);

  return (
    <div className="grid gap-2 lg:grid-cols-2">
      {FAIRNESS_METRIC_DEFS.map((m) => (
        <div key={m.key} className="rounded border border-border bg-surface-raised p-2">
          <h3 className="mb-1 text-sm font-semibold text-text">{m.label}</h3>
          <div className="h-[180px] w-full" role="img" aria-label={`${m.label} B2 versus B3`}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: c.faint, fontSize: 10 }} tickLine={false} axisLine={{ stroke: c.border }} minTickGap={32} />
                <YAxis tick={{ fill: c.faint, fontSize: 10 }} tickLine={false} axisLine={false} width={36} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 4, fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey={`${m.key}_b3`}
                  name="B3 (full)"
                  stroke={c.accent}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey={`${m.key}_b2`}
                  name="B2 (SDR only)"
                  stroke={c.warning}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </div>
  );
}
