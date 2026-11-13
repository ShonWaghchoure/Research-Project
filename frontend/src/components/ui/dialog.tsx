"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40 animate-fade-in" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded border border-border bg-surface-raised p-3 shadow-none animate-fade-in focus:outline-none",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div>
            <DialogPrimitive.Title className="text-base font-semibold text-text">{title}</DialogPrimitive.Title>
            {description && (
              <DialogPrimitive.Description className="mt-0.5 text-xs text-text-muted">
                {description}
              </DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close
            className="rounded p-0.5 text-text-muted hover:bg-surface-sunken hover:text-text"
            aria-label="Close"
          >
            <X className="h-2 w-2" />
          </DialogPrimitive.Close>
        </div>
        <div className="mt-2">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
