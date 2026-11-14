"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api, ApiError } from "@/lib/api/client";
import type { SimControlState } from "@/lib/api/types";

export function SimControls() {
  const [state, setState] = useState<SimControlState | null>(null);
  const [seconds, setSeconds] = useState("45");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    const s = await api.admin.simulation.get();
    setState(s);
    setSeconds(String(s.interval_seconds));
  };

  useEffect(() => {
    void refresh().catch((err) =>
      setError(err instanceof ApiError ? err.detail : "Failed to load simulation state"),
    );
  }, []);

  const act = async (fn: () => Promise<SimControlState>) => {
    setBusy(true);
    setError(null);
    try {
      const s = await fn();
      setState(s);
      setSeconds(String(s.interval_seconds));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Simulation control failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-text-muted">Clock</span>
        {state ? (
          <Badge tone={state.running ? "success" : "warning"}>
            {state.running ? "running" : "stopped"}
          </Badge>
        ) : (
          <span className="text-text-faint">…</span>
        )}
        {state && (
          <span className="num text-text-muted">
            {state.interval_seconds}s
            {state.override_active ? " (override)" : ""}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <Button disabled={busy} onClick={() => void act(() => api.admin.simulation.start())}>
          Start
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => void act(() => api.admin.simulation.stop())}
        >
          Stop
        </Button>
        <Field id="sim-speed" label="Interval length" unit="s" className="w-36">
          <Input
            type="number"
            min={5}
            max={3600}
            value={seconds}
            onChange={(e) => setSeconds(e.target.value)}
          />
        </Field>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() =>
            void act(() => api.admin.simulation.speed(Number(seconds)))
          }
        >
          Set speed
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
