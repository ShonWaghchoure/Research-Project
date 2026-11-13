import { Badge } from "@/components/ui/badge";
import type { Trade } from "@/lib/api/types";
import { formatInr, formatKwh, formatTime, paiseToInr, paymentPaise } from "@/lib/format";
import { shortAddress } from "@/lib/utils";

const STATUS: Record<Trade["status"], { label: string; tone: "neutral" | "accent" | "success" | "warning" }> = {
  cleared: { label: "Cleared", tone: "accent" },
  settled: { label: "Settled", tone: "neutral" },
  delivered: { label: "Delivered", tone: "success" },
  shortfall: { label: "Shortfall", tone: "warning" },
};

/** Compact trades table. Pseudonymous addresses; units in every header. */
export function TradesTable({ trades, mine = false, compact = false }: { trades: Trade[]; mine?: boolean; compact?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-text-muted">
            <th scope="col" className="px-3 py-1 font-medium">Time</th>
            <th scope="col" className="px-2 py-1 font-medium">Interval</th>
            {mine && <th scope="col" className="px-2 py-1 font-medium">Side</th>}
            {!compact && <th scope="col" className="px-2 py-1 font-medium">{mine ? "Counterparty" : "Buyer → seller"}</th>}
            <th scope="col" className="px-2 py-1 text-right font-medium">Quantity (kWh)</th>
            <th scope="col" className="px-2 py-1 text-right font-medium">Price (₹/kWh)</th>
            <th scope="col" className="px-2 py-1 text-right font-medium">Value (₹)</th>
            <th scope="col" className="px-3 py-1 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const s = STATUS[t.status];
            const cp = t.side === "buy" ? t.seller : t.buyer;
            return (
              <tr key={t.id} className="border-b border-border last:border-0" data-testid="trade-row">
                <td className="num whitespace-nowrap px-3 py-1 text-text-muted">{formatTime(t.created_at)}</td>
                <td className="num px-2 py-1">#{t.interval_id}</td>
                {mine && (
                  <td className="px-2 py-1">
                    <Badge tone={t.side === "buy" ? "accent" : "neutral"}>{t.side === "buy" ? "Buy" : "Sell"}</Badge>
                  </td>
                )}
                {!compact && (
                  <td className="num whitespace-nowrap px-2 py-1 font-mono text-xs text-text-muted">
                    {mine ? shortAddress(cp) : `${shortAddress(t.buyer)} → ${shortAddress(t.seller)}`}
                  </td>
                )}
                <td className="num px-2 py-1 text-right">{formatKwh(t.qty_wh, false)}</td>
                <td className="num px-2 py-1 text-right">{paiseToInr(t.price_paise)}</td>
                <td className="num px-2 py-1 text-right">{formatInr(paymentPaise(t.qty_wh, t.price_paise)).slice(1)}</td>
                <td className="px-3 py-1">
                  <Badge tone={s.tone}>{s.label}</Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
