"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Orderbook } from "@/lib/api/types";
import { useChartColors } from "@/lib/chart-theme";
import { formatKwh, paiseToInr } from "@/lib/format";

/** Anonymised cumulative depth from the order book (bids left, asks right). */
export function DepthChart({ book }: { book: Orderbook }) {
  const c = useChartColors();
  const bidLevels = [...book.bids].sort((a, b) => b.price_paise - a.price_paise);
  const askLevels = [...book.asks].sort((a, b) => a.price_paise - b.price_paise);

  let bidCum = 0;
  const bids = bidLevels.map((l) => {
    bidCum += l.qty_wh;
    return { price: l.price_paise / 100, bid: bidCum / 1000, ask: 0, side: "bid" as const };
  });
  let askCum = 0;
  const asks = askLevels.map((l) => {
    askCum += l.qty_wh;
    return { price: l.price_paise / 100, bid: 0, ask: askCum / 1000, side: "ask" as const };
  });
  const rows = [...bids.reverse(), ...asks];

  return (
    <div className="h-[240px] w-full" role="img" aria-label="Anonymised order book depth">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap={2}>
          <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="price"
            tick={{ fill: c.faint, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: c.border }}
            tickFormatter={(v) => `₹${Number(v).toFixed(1)}`}
          />
          <YAxis
            tick={{ fill: c.faint, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
            tickFormatter={(v) => `${Number(v).toFixed(1)}`}
            label={{ value: "kWh cum.", angle: -90, position: "insideLeft", fill: c.faint, fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 4, fontSize: 12 }}
            formatter={(value, name) => {
              const n = typeof value === "number" ? value : Number(value);
              if (!n) return [null, null];
              return [`${n.toFixed(2)} kWh`, name === "bid" ? "Bid depth" : "Ask depth"];
            }}
            labelFormatter={(label) => `₹${Number(label).toFixed(2)} / kWh`}
          />
          <Bar dataKey="bid" stackId="d" fill={c.buy} isAnimationActive={false} name="bid" />
          <Bar dataKey="ask" stackId="d" fill={c.sell} isAnimationActive={false} name="ask" />
        </BarChart>
      </ResponsiveContainer>
      <dl className="mt-1 grid grid-cols-2 gap-1 px-1 text-xs">
        <div>
          <dt className="text-text-muted">Total demand</dt>
          <dd className="num text-text">{formatKwh(book.demand_wh)}</dd>
        </div>
        <div>
          <dt className="text-text-muted">Total supply</dt>
          <dd className="num text-text">{formatKwh(book.supply_wh)}</dd>
        </div>
      </dl>
      <p className="sr-only">
        Bids up to ₹{paiseToInr(bidLevels[0]?.price_paise)} and asks from ₹{paiseToInr(askLevels[0]?.price_paise)}.
      </p>
    </div>
  );
}
