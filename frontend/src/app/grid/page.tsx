"use client";

import { FeederMapPanel } from "@/components/grid/feeder-map";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { QueryState } from "@/components/ui/data-state";
import { formatPct } from "@/lib/format";
import { useGridStatus } from "@/lib/queries";

export default function GridPage() {
  const grid = useGridStatus();

  return (
    <>
      <PageHeader
        title="Grid map"
        description="The 13-node radial feeder with live line loadings. Congested lines are highlighted; click a node for its participants."
      />

      <div className="mb-3 grid grid-cols-2 gap-1 md:grid-cols-4">
        <Stat label="Interval" value={grid.data ? `#${grid.data.interval_id}` : "—"} />
        <Stat
          label="Peak loading"
          value={grid.data ? formatPct(grid.data.max_loading_pct, false) : "—"}
        />
        <Stat
          label="Congested lines"
          value={grid.data ? String(grid.data.congested_line_ids.length) : "—"}
          hint={grid.data && grid.data.congested_line_ids.length === 0 ? "All clear" : "Above 70% of capacity"}
        />
        <Stat
          label="P2P share"
          value={grid.data ? formatPct(grid.data.p2p_share_pct, false) : "—"}
          hint="Of energy that stayed on the feeder"
        />
      </div>

      <Card>
        <CardHeader title="Feeder tree" description="Transformer at the top; branches are distribution laterals" />
        <QueryState query={grid} rows={6}>
          {(g) => (
            <CardBody>
              <FeederMapPanel grid={g} />
            </CardBody>
          )}
        </QueryState>
      </Card>
    </>
  );
}
