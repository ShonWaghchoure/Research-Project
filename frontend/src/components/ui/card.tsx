import * as React from "react";
import { cn } from "@/lib/utils";

/** The one card style used everywhere: raised surface, 1px border, no shadow. */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn("min-w-0 rounded border border-border bg-surface-raised", className)}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex items-start justify-between gap-2 border-b border-border px-3 py-2", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-text">{title}</h2>
        {description && <p className="mt-0.5 text-xs text-text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </header>
  );
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-3 py-3", className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <footer
      className={cn("flex items-center justify-end gap-1 border-t border-border px-3 py-2", className)}
      {...props}
    />
  );
}

/** Key figure used in the "key figures" row at the top of every page. */
export function Stat({
  label,
  value,
  unit,
  hint,
  className,
  live,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  hint?: React.ReactNode;
  className?: string;
  /** Announce changes to screen readers. */
  live?: boolean;
}) {
  return (
    <div className={cn("rounded border border-border bg-surface-raised px-3 py-2", className)}>
      <div className="text-xs uppercase tracking-wide text-text-muted">{label}</div>
      <div
        className="num mt-0.5 flex items-baseline gap-0.5 text-xl font-medium text-text"
        aria-live={live ? "polite" : undefined}
        aria-atomic={live ? true : undefined}
      >
        <span>{value}</span>
        {unit && <span className="text-sm font-normal text-text-muted">{unit}</span>}
      </div>
      {hint && <div className="mt-0.5 text-xs text-text-faint">{hint}</div>}
    </div>
  );
}
