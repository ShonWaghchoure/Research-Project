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
import type { AttackRunResult } from "@/lib/api/types";
import { useChartColors } from "@/lib/chart-theme";

function mergeSeries(off?: AttackRunResult | null, on?: AttackRunResult | null) {
  const map = new Map<number, Record<string, number | null>>();
  for (const p of off?.series ?? []) {
    map.set(p.interval, {
      interval: p.interval,
      p_off: p.p_ref ?? null,
      jain_off: p.jain ?? null,
      rep_off: p.mean_reputation ?? null,
    });
  }
  for (const p of on?.series ?? []) {
    const row = map.get(p.interval) ?? { interval: p.interval };
    map.set(p.interval, {
      ...row,
      p_on: p.p_ref ?? null,
      jain_on: p.jain ?? null,
      rep_on: p.mean_reputation ?? null,
    });
  }
  return [...map.values()].sort((a, b) => Number(a.interval) - Number(b.interval));
}

export function DefenseCharts({
  off,
  on,
}: {
  off: AttackRunResult | null;
  on: AttackRunResult | null;
}) {
  const colors = useChartColors();
  const data = mergeSeries(off, on);
  if (!data.length) {
    return <p className="text-sm text-text-muted">Run the scenario with defenses off and on to compare.</p>;
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <ChartBlock title="Reference price" unit="paise/kWh">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
            <XAxis dataKey="interval" tick={{ fill: colors.faint, fontSize: 11 }} />
            <YAxis tick={{ fill: colors.faint, fontSize: 11 }} width={48} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="p_off" name="Defenses off" stroke={colors.danger} dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="p_on" name="Defenses on" stroke={colors.success} dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </ChartBlock>
      <ChartBlock title="Jain index" unit="0–1">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={colors.border} strokeDasharray="3 3" />
            <XAxis dataKey="interval" tick={{ fill: colors.faint, fontSize: 11 }} />
            <YAxis domain={[0, 1]} tick={{ fill: colors.faint, fontSize: 11 }} width={36} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="jain_off" name="Defenses off" stroke={colors.danger} dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="jain_on" name="Defenses on" stroke={colors.success} dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </ChartBlock>
    </div>
  );
}

function ChartBlock({ title, unit, children }: { title: string; unit: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-sm font-medium text-text">
        {title} <span className="font-normal text-text-muted">({unit})</span>
      </h3>
      {children}
    </div>
  );
}
