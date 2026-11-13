import * as React from "react";
import { cn } from "@/lib/utils";

const control =
  "h-5 w-full rounded border border-border-strong bg-surface-raised px-2 text-sm text-text placeholder:text-text-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-surface disabled:opacity-50 aria-[invalid=true]:border-danger";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input ref={ref} type={type} className={cn(control, type === "number" && "num", className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn(control, "pr-4", className)} {...props}>
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-xs font-medium text-text", className)} {...props} />;
}

/**
 * Label + control + unit + help/error. Units are always shown next to the control
 * so a value is never read without one.
 */
export function Field({
  id,
  label,
  unit,
  help,
  error,
  children,
  className,
}: {
  id: string;
  label: string;
  unit?: string;
  help?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const helpId = help ? `${id}-help` : undefined;
  const errId = error ? `${id}-err` : undefined;
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <Label htmlFor={id}>
        {label}
        {unit && <span className="ml-0.5 font-normal text-text-muted">({unit})</span>}
      </Label>
      {React.isValidElement(children)
        ? React.cloneElement(children as React.ReactElement, {
            id,
            "aria-invalid": error ? true : undefined,
            "aria-describedby": [helpId, errId].filter(Boolean).join(" ") || undefined,
          })
        : children}
      {help && !error && (
        <p id={helpId} className="text-xs text-text-muted">
          {help}
        </p>
      )}
      {error && (
        <p id={errId} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** Accessible radio group rendered as a segmented control. */
export function Segmented<T extends string>({
  name,
  value,
  onChange,
  options,
  label,
}: {
  name: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; description?: string }[];
  label: string;
}) {
  return (
    <fieldset className="flex flex-col gap-0.5">
      <legend className="text-xs font-medium text-text">{label}</legend>
      <div role="radiogroup" className="grid gap-1" style={{ gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
        {options.map((o) => {
          const checked = o.value === value;
          return (
            <label
              key={o.value}
              className={cn(
                "cursor-pointer rounded border px-2 py-1 text-sm transition-colors focus-within:ring-2 focus-within:ring-accent focus-within:ring-offset-1 focus-within:ring-offset-surface",
                checked
                  ? "border-accent bg-accent-soft text-text"
                  : "border-border-strong bg-surface-raised text-text-muted hover:bg-surface-sunken",
              )}
            >
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={checked}
                onChange={() => onChange(o.value)}
                className="sr-only"
              />
              <span className="font-medium">{o.label}</span>
              {o.description && <span className="block text-xs text-text-muted">{o.description}</span>}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
