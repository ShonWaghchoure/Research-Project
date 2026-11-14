"use client";

import type { HashTriple } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function MatchBadge({ ok }: { ok: boolean | null | undefined }) {
  if (ok === null || ok === undefined) {
    return <span className="text-xs text-text-faint">n/a</span>;
  }
  return (
    <span className={cn("text-xs font-medium", ok ? "text-success" : "text-danger")}>
      {ok ? "match" : "mismatch"}
    </span>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-1 text-xs">
      <span className="text-text-muted">{label}</span>
      <code className="break-all font-mono text-text">{value ?? "—"}</code>
    </div>
  );
}

export function HashCompare({
  title,
  triple,
}: {
  title: string;
  triple: HashTriple;
}) {
  return (
    <div className="rounded border border-border bg-surface-raised p-2" aria-label={title}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-text">{title}</h3>
        <div className="flex gap-2">
          <span className="text-xs text-text-muted">
            stored↔recomputed <MatchBadge ok={triple.stored_matches_recomputed} />
          </span>
          <span className="text-xs text-text-muted">
            stored↔chain <MatchBadge ok={triple.stored_matches_on_chain} />
          </span>
        </div>
      </div>
      <div className="space-y-1">
        <Row label="Stored" value={triple.stored} />
        <Row label="Recomputed" value={triple.recomputed} />
        <Row label="On chain" value={triple.on_chain} />
      </div>
    </div>
  );
}
