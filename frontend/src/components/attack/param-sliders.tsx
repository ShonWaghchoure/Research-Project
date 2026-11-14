"use client";

import { Field, Input } from "@/components/ui/field";

export interface AttackParams {
  participants: number;
  days: number;
  seed: number;
  max_intervals: number;
}

export function ParamSliders({
  value,
  onChange,
}: {
  value: AttackParams;
  onChange: (next: AttackParams) => void;
}) {
  const set = (key: keyof AttackParams, raw: string) => {
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    onChange({ ...value, [key]: n });
  };

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      <Field id="atk-participants" label="Participants" unit="count">
        <Input
          type="number"
          min={10}
          max={200}
          value={value.participants}
          onChange={(e) => set("participants", e.target.value)}
        />
      </Field>
      <Field id="atk-days" label="Simulated days" unit="days" help="Capped by max intervals below.">
        <Input
          type="number"
          min={1}
          max={3}
          value={value.days}
          onChange={(e) => set("days", e.target.value)}
        />
      </Field>
      <Field id="atk-intervals" label="Max intervals" unit="slots">
        <Input
          type="number"
          min={12}
          max={288}
          value={value.max_intervals}
          onChange={(e) => set("max_intervals", e.target.value)}
        />
      </Field>
      <Field id="atk-seed" label="Seed" unit="int">
        <Input
          type="number"
          min={0}
          value={value.seed}
          onChange={(e) => set("seed", e.target.value)}
        />
      </Field>
    </div>
  );
}
