"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

export function Tooltip({ content, children }: { content: React.ReactNode; children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded border border-border bg-surface-raised px-2 py-1 text-xs text-text animate-fade-in"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-[var(--border)]" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/** Small "i" button that opens an explanation; keyboard and screen-reader friendly. */
export function InfoTip({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <Tooltip content={children}>
      <button
        type="button"
        aria-label={label}
        className={cn("inline-flex rounded text-text-faint hover:text-text", className)}
      >
        <Info className="h-2 w-2" aria-hidden />
      </button>
    </Tooltip>
  );
}
