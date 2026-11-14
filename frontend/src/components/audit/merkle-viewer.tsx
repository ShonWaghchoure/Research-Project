"use client";

export function MerkleViewer({
  leaves,
}: {
  leaves: Record<string, unknown>[];
}) {
  if (!leaves.length) {
    return <p className="text-sm text-text-muted">No revealed positions to show as Merkle leaves.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] text-left text-xs">
        <thead className="text-text-muted">
          <tr className="border-b border-border">
            <th className="py-1 pr-2 font-medium">Participant</th>
            <th className="py-1 pr-2 font-medium">Side</th>
            <th className="py-1 pr-2 font-medium">Qty (kWh)</th>
            <th className="py-1 pr-2 font-medium">Limit</th>
            <th className="py-1 font-medium">Leaf</th>
          </tr>
        </thead>
        <tbody>
          {leaves.map((leaf, i) => (
            <tr key={i} className="border-b border-border/60">
              <td className="num py-1 pr-2">{String(leaf.participant_id)}</td>
              <td className="py-1 pr-2">{String(leaf.side)}</td>
              <td className="num py-1 pr-2">{Number(leaf.qty_kwh).toFixed(3)}</td>
              <td className="num py-1 pr-2">{Number(leaf.limit_price).toFixed(0)}</td>
              <td className="max-w-[14rem] truncate font-mono" title={String(leaf.leaf)}>
                {String(leaf.leaf)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
