import * as React from "react";
import { Check, Circle, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepStatus = "todo" | "active" | "done" | "failed";

export interface Step {
  id: string;
  title: string;
  description?: React.ReactNode;
  status: StepStatus;
}

const ICON: Record<StepStatus, React.ReactNode> = {
  todo: <Circle className="h-2 w-2 text-text-faint" aria-hidden />,
  active: <Loader2 className="h-2 w-2 animate-spin text-accent" aria-hidden />,
  done: <Check className="h-2 w-2 text-success" aria-hidden />,
  failed: <XCircle className="h-2 w-2 text-danger" aria-hidden />,
};

const TEXT: Record<StepStatus, string> = {
  todo: "not started",
  active: "in progress",
  done: "done",
  failed: "failed",
};

/** Vertical stepper. Status is conveyed by icon, text and colour together. */
export function Stepper({ steps, className }: { steps: Step[]; className?: string }) {
  return (
    <ol className={cn("flex flex-col", className)}>
      {steps.map((s, i) => (
        <li key={s.id} className="relative flex gap-2 pb-2 last:pb-0" aria-current={s.status === "active" ? "step" : undefined}>
          {i < steps.length - 1 && (
            <span aria-hidden className="absolute left-[9px] top-[22px] h-[calc(100%-22px)] w-px bg-border" />
          )}
          <span className="mt-0.5 flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full border border-border bg-surface-raised">
            {ICON[s.status]}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-1">
              <span className={cn("text-sm font-medium", s.status === "todo" ? "text-text-muted" : "text-text")}>
                {i + 1}. {s.title}
              </span>
              <span className="text-xs text-text-faint">{TEXT[s.status]}</span>
            </div>
            {s.description && <div className="mt-0.5 text-xs text-text-muted">{s.description}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}
