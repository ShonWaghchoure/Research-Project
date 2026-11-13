"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PricePoint } from "@/lib/api/types";
import { P_FIT_PAISE, P_RET_PAISE, useChartColors } from "@/lib/chart-theme";
import { paiseToInr } from "@/lib/format";

/** Live clearing price against the feed-in / retail tariff band. */
export function PriceBandChart({ data }: { data: PricePoint[] }) {
  const c = useChartColors();
  const rows = data.map((p) => ({
    ...p,
    label: `#${p.interval_id}`,
    price: p.p_ref_paise / 100,
    fit: P_FIT_PAISE / 100,
    ret: P_RET_PAISE / 100,
  }));

  return (
    <div className="h-[260px] w-full" role="img" aria-label="Reference price over recent intervals against the tariff band">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: c.faint, fontSize: 11 }} tickLine={false} axisLine={{ stroke: c.border }} minTickGap={24} />
          <YAxis
            domain={[2.5, 8.5]}
            tick={{ fill: c.faint, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `₹${Number(v).toFixed(0)}`}
            width={40}
            label={{ value: "₹/kWh", angle: -90, position: "insideLeft", fill: c.faint, fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 4, fontSize: 12 }}
            formatter={(value, name) => {
              const n = typeof value === "number" ? value : Number(value);
              if (name === "price") return [`₹${n.toFixed(2)} / kWh`, "Reference price"];
              return [String(value), String(name)];
            }}
            labelFormatter={(label) => `Interval ${label}`}
          />
          <ReferenceArea y1={P_FIT_PAISE / 100} y2={P_RET_PAISE / 100} fill={c.band} fillOpacity={0.55} ifOverflow="extendDomain" />
          <Area type="monotone" dataKey="price" stroke="none" fill={c.accent} fillOpacity={0.12} isAnimationActive={false} />
          <Line type="monotone" dataKey="price" stroke={c.accent} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <p className="mt-1 px-1 text-xs text-text-muted">
        Band is feed-in ₹{paiseToInr(P_FIT_PAISE)} to retail ₹{paiseToInr(P_RET_PAISE)} per kWh. Price is the single clearing price for the interval.
      </p>
    </div>
  );
}
