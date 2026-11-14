"use client";

export function ExplorerLinks({
  explorer,
}: {
  explorer: Record<string, string | null | undefined>;
}) {
  const network = explorer.network ?? "—";
  const settlement = explorer.settlement;
  const hint = explorer.interval_hint;
  const url = explorer.block_explorer;

  return (
    <dl className="grid gap-1 text-sm sm:grid-cols-2">
      <div>
        <dt className="text-xs text-text-muted">Network</dt>
        <dd className="text-text">{network}</dd>
      </div>
      <div>
        <dt className="text-xs text-text-muted">Settlement</dt>
        <dd className="break-all font-mono text-xs text-text">{settlement ?? "—"}</dd>
      </div>
      {hint && (
        <div className="sm:col-span-2">
          <dt className="text-xs text-text-muted">On-chain lookup</dt>
          <dd className="font-mono text-xs text-text">{hint}</dd>
        </div>
      )}
      <div className="sm:col-span-2">
        <dt className="text-xs text-text-muted">Block explorer</dt>
        <dd>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-accent underline-offset-2 hover:underline"
            >
              Open Settlement on explorer
            </a>
          ) : (
            <span className="text-text-muted">
              No public explorer for this network (local Hardhat).
            </span>
          )}
        </dd>
      </div>
    </dl>
  );
}
