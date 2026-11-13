import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * State badge. Never colour alone: every tone is paired with the text and, where
 * the caller provides one, an icon.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-0.5 rounded border px-1 py-px text-xs font-medium leading-4",
  {
    variants: {
      tone: {
        neutral: "border-border bg-surface-sunken text-text-muted",
        accent: "border-accent/30 bg-accent-soft text-accent",
        success: "border-success/30 bg-success-soft text-success",
        warning: "border-warning/30 bg-warning-soft text-warning",
        danger: "border-danger/30 bg-danger-soft text-danger",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode;
}

export function Badge({ className, tone, icon, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
      {icon}
      {children}
    </span>
  );
}
