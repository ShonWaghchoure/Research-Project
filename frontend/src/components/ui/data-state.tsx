import * as React from "react";
import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
import { Button } from "./button";
import { SkeletonRows } from "./skeleton";
import { cn } from "@/lib/utils";

/**
 * Every data view renders through one of these three so loading, empty and error
 * states look the same everywhere and always offer a retry.
 */
export function Loading({ rows = 4, label = "Loading", className }: { rows?: number; label?: string; className?: string }) {
  return (
    <div role="status" aria-label={label} className={cn("px-3 py-3", className)}>
      <SkeletonRows rows={rows} />
    </div>
  );
}

export function Empty({
  title,
  hint,
  action,
  className,
}: {
  title: string;
  hint?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-1 px-3 py-5 text-center", className)}>
      <Inbox className="h-3 w-3 text-text-faint" aria-hidden />
      <p className="text-sm font-medium text-text">{title}</p>
      {hint && <p className="max-w-sm text-xs text-text-muted">{hint}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-1 px-3 py-5 text-center", className)}>
      <AlertCircle className="h-3 w-3 text-danger" aria-hidden />
      <p className="text-sm font-medium text-text">Could not load this</p>
      <p className="max-w-sm text-xs text-text-muted">{message}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry} className="mt-1">
          <RefreshCw className="h-2 w-2" aria-hidden /> Retry
        </Button>
      )}
    </div>
  );
}

/** Pick the right state for a TanStack query result. */
export function QueryState<T>({
  query,
  empty,
  children,
  rows,
}: {
  query: {
    data: T | undefined;
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  empty?: { when: (d: T) => boolean; title: string; hint?: React.ReactNode; action?: React.ReactNode };
  children: (data: T) => React.ReactNode;
  rows?: number;
}) {
  if (query.isPending) return <Loading rows={rows} />;
  if (query.isError)
    return (
      <ErrorState
        message={(query.error as Error)?.message ?? "Unknown error"}
        onRetry={() => query.refetch()}
      />
    );
  const data = query.data as T;
  if (empty && empty.when(data)) return <Empty title={empty.title} hint={empty.hint} action={empty.action} />;
  return <>{children(data)}</>;
}
