import { CheckCircle2, Clock, PenLine, XCircle } from "lucide-react";
import type { TxState } from "@/lib/tx";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const META = {
  idle: null,
  signing: { icon: PenLine, text: "Awaiting your signature", tone: "text-text-muted" },
  pending: { icon: Clock, text: "Transaction pending", tone: "text-warning" },
  confirmed: { icon: CheckCircle2, text: "Confirmed on chain", tone: "text-success" },
  failed: { icon: XCircle, text: "Transaction failed", tone: "text-danger" },
} as const;

/** Shared transaction status line: icon + text + hash + readable failure reason. */
export function TxStatusLine({ tx, onRetry, className }: { tx: TxState; onRetry?: () => void; className?: string }) {
  const m = META[tx.status];
  if (!m) return null;
  const Icon = m.icon;
  return (
    <div role="status" aria-live="polite" className={cn("flex flex-col gap-0.5 rounded border border-border bg-surface-sunken px-2 py-1 text-xs", className)}>
      <div className={cn("flex items-center gap-1 font-medium", m.tone)}>
        <Icon className="h-2 w-2" aria-hidden />
        {m.text}
      </div>
      {tx.hash && (
        <div className="num break-all font-mono text-text-faint" title={tx.hash}>
          {tx.hash}
        </div>
      )}
      {tx.error && (
        <div className="flex items-start justify-between gap-1">
          <p className="text-text">{tx.error}</p>
          {onRetry && (
            <Button size="sm" onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
