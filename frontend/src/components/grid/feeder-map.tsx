"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { GridNode, GridStatus } from "@/lib/api/types";
import { formatPct } from "@/lib/format";
import { cn, shortAddress } from "@/lib/utils";

/** Fixed radial layout for the 13-node feeder (n0 at top). */
const LAYOUT: Record<string, { x: number; y: number }> = {
  n0: { x: 280, y: 36 },
  n1: { x: 120, y: 120 },
  n2: { x: 280, y: 120 },
  n3: { x: 440, y: 120 },
  n4: { x: 40, y: 220 },
  n5: { x: 120, y: 220 },
  n6: { x: 200, y: 220 },
  n7: { x: 280, y: 220 },
  n8: { x: 400, y: 220 },
  n9: { x: 480, y: 220 },
  n10: { x: 280, y: 320 },
  n11: { x: 220, y: 400 },
  n12: { x: 340, y: 400 },
};

function loadingTone(pct: number, congested: boolean): string {
  if (congested || pct >= 70) return "var(--warning)";
  if (pct >= 50) return "var(--accent)";
  return "var(--border-strong)";
}

/** Interactive SVG feeder tree with line loadings and clickable nodes. */
export function FeederMap({ grid, selectedId, onSelect }: {
  grid: GridStatus;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const byId = useMemo(() => {
    const m = new Map<string, GridNode>();
    for (const n of grid.nodes ?? []) m.set(n.id, n);
    return m;
  }, [grid.nodes]);

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox="0 0 560 440"
        className="mx-auto h-auto w-full max-w-[560px]"
        role="img"
        aria-label="Radial feeder tree with line loadings"
      >
        {grid.lines.map((line) => {
          const a = LAYOUT[line.from_node];
          const b = LAYOUT[line.to_node];
          if (!a || !b) return null;
          const congested = grid.congested_line_ids.includes(line.id);
          const stroke = loadingTone(line.loading_pct, congested);
          const width = congested ? 4 : 2 + Math.min(3, line.loading_pct / 40);
          return (
            <g key={line.id}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={stroke}
                strokeWidth={width}
                strokeLinecap="round"
              >
                <title>
                  {line.from_node}→{line.to_node}: {Math.round(line.loading_pct)}% of {line.capacity_kw} kW
                  {congested ? " (congested)" : ""}
                </title>
              </line>
              {congested && (
                <circle
                  cx={(a.x + b.x) / 2}
                  cy={(a.y + b.y) / 2}
                  r={4}
                  fill="var(--warning)"
                  aria-hidden
                />
              )}
            </g>
          );
        })}
        {Object.entries(LAYOUT).map(([id, pos]) => {
          const node = byId.get(id);
          const selected = selectedId === id;
          const isRoot = id === "n0";
          const count = node?.participants.length ?? 0;
          return (
            <g key={id}>
              <circle
                cx={pos.x}
                cy={pos.y}
                r={isRoot ? 16 : 14}
                fill={selected ? "var(--accent-soft)" : "var(--surface-raised)"}
                stroke={selected ? "var(--accent)" : "var(--border-strong)"}
                strokeWidth={selected ? 2.5 : 1.5}
                className="cursor-pointer"
                tabIndex={0}
                role="button"
                aria-pressed={selected}
                aria-label={`Node ${id}${count ? `, ${count} participants` : ""}`}
                onClick={() => onSelect(selected ? null : id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(selected ? null : id);
                  }
                }}
              />
              <text
                x={pos.x}
                y={pos.y + 4}
                textAnchor="middle"
                fontSize={10}
                fontWeight={600}
                fill="var(--text)"
                className="pointer-events-none select-none"
              >
                {isRoot ? "T" : id.replace("n", "")}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-1 text-xs text-text-muted">
        Line colour and thickness show loading. Warning marks are congested (&gt;70%). Click a node for its participants.
      </p>
    </div>
  );
}

export function NodeParticipants({ grid, nodeId }: { grid: GridStatus; nodeId: string | null }) {
  const node = grid.nodes?.find((n) => n.id === nodeId);
  if (!nodeId || !node) {
    return (
      <p className="text-sm text-text-muted">Select a feeder node to see who is attached (pseudonymous addresses).</p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1">
        <h3 className="text-sm font-semibold text-text">{node.label}</h3>
        <Badge tone={node.kind === "root" ? "accent" : "neutral"}>
          {node.kind === "root" ? "Transformer" : "Feeder node"}
        </Badge>
      </div>
      {node.participants.length === 0 ? (
        <p className="text-sm text-text-muted">No participants on this node right now.</p>
      ) : (
        <ul className="flex max-h-[280px] flex-col gap-0.5 overflow-y-auto" aria-label={`Participants on ${node.id}`}>
          {node.participants.map((p) => (
            <li
              key={p.address}
              className={cn("flex items-center justify-between rounded border border-border px-2 py-1 text-xs")}
            >
              <span className="num font-mono text-text">{shortAddress(p.address, 5)}</span>
              <Badge tone="neutral">{p.kind}</Badge>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-text-muted">
        Peak loading this interval: <span className="num text-text">{formatPct(grid.max_loading_pct, false)}</span>
      </p>
    </div>
  );
}

/** Thin wrapper that owns selection state for the map + side panel. */
export function FeederMapPanel({ grid }: { grid: GridStatus }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="grid gap-2 lg:grid-cols-[1fr_220px]">
      <FeederMap grid={grid} selectedId={selected} onSelect={setSelected} />
      <NodeParticipants grid={grid} nodeId={selected} />
    </div>
  );
}
