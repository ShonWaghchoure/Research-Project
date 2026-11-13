"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { QueryState } from "@/components/ui/data-state";
import { useGridStatus } from "@/lib/queries";
import { formatPct } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Feeder status: worst line loading, congested lines, and the P2P share of energy. */
export function GridStatusCard() {
  const q = useGridStatus();
  return (
    <Card>
      <CardHeader title="Grid status" description="Local feeder, 13 nodes" />
      <QueryState query={q} rows={3}>
        {(g) => {
          const ok = g.congested_line_ids.length === 0;
          const top = [...g.lines].sort((a, b) => b.loading_pct - a.loading_pct).slice(0, 4);
          return (
            <CardBody className="flex flex-col gap-2">
              <div className={cn("flex items-center gap-1 text-sm font-medium", ok ? "text-success" : "text-warning")}>
                {ok ? <CheckCircle2 className="h-2 w-2" aria-hidden /> : <AlertTriangle className="h-2 w-2" aria-hidden />}
                {ok ? "No congested lines" : `${g.congested_line_ids.length} congested line${g.congested_line_ids.length > 1 ? "s" : ""}`}
              </div>
              <dl className="grid grid-cols-2 gap-1 text-xs">
                <div>
                  <dt className="text-text-muted">Peak line loading</dt>
                  <dd className="num text-base text-text">{formatPct(g.max_loading_pct, false)}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Energy traded peer-to-peer</dt>
                  <dd className="num text-base text-text">{formatPct(g.p2p_share_pct, false)}</dd>
                </div>
              </dl>
              <ul className="flex flex-col gap-0.5" aria-label="Most loaded lines">
                {top.map((l) => {
                  const congested = g.congested_line_ids.includes(l.id);
                  return (
                    <li key={l.id} className="flex items-center gap-1 text-xs">
                      <span className="num w-10 shrink-0 font-mono text-text-muted">
                        {l.from_node}→{l.to_node}
                      </span>
                      <span className="h-[6px] flex-1 overflow-hidden rounded-full bg-surface-sunken" aria-hidden>
                        <span
                          className={cn("block h-full", congested ? "bg-warning" : "bg-accent")}
                          style={{ width: `${Math.min(100, l.loading_pct)}%` }}
                        />
                      </span>
                      <span className="num w-5 text-right text-text">{Math.round(l.loading_pct)}%</span>
                      {congested && <span className="sr-only">congested</span>}
                    </li>
                  );
                })}
              </ul>
            </CardBody>
          );
        }}
      </QueryState>
    </Card>
  );
}
