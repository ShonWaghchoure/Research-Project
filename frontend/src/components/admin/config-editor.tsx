"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/field";
import { api, ApiError } from "@/lib/api/client";

function stringifyValue(v: unknown): string {
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

function parseValue(raw: string, previous: unknown): number | string | boolean {
  const trimmed = raw.trim();
  if (typeof previous === "boolean") return trimmed === "true";
  if (typeof previous === "number") {
    const n = Number(trimmed);
    if (!Number.isFinite(n)) throw new Error("must be a number");
    return n;
  }
  if (trimmed === "true" || trimmed === "false") return trimmed === "true";
  const asNum = Number(trimmed);
  if (trimmed !== "" && Number.isFinite(asNum) && /^-?\d+(\.\d+)?$/.test(trimmed)) return asNum;
  return trimmed;
}

export function ConfigEditor() {
  const [values, setValues] = useState<Record<string, number | string | boolean>>({});
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    setError(null);
    const cfg = await api.admin.config.get();
    setValues(cfg.values);
    const next: Record<string, string> = {};
    for (const [k, v] of Object.entries(cfg.values)) next[k] = stringifyValue(v);
    setDraft(next);
  };

  useEffect(() => {
    void reload().catch((err) =>
      setError(err instanceof ApiError ? err.detail : "Failed to load config"),
    );
  }, []);

  const diffs = Object.keys(draft).filter((k) => {
    try {
      return stringifyValue(parseValue(draft[k], values[k])) !== stringifyValue(values[k]);
    } catch {
      return true;
    }
  });

  const save = async () => {
    setError(null);
    setSaved(null);
    const updates: Record<string, unknown> = {};
    try {
      for (const key of diffs) {
        updates[key] = parseValue(draft[key], values[key]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid value");
      return;
    }
    if (!Object.keys(updates).length) {
      setSaved("No changes.");
      return;
    }
    setBusy(true);
    try {
      const cfg = await api.admin.config.put(updates);
      setValues(cfg.values);
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(cfg.values)) next[k] = stringifyValue(v);
      setDraft(next);
      setSaved(`Saved ${Object.keys(updates).length} key(s).`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const keys = Object.keys(draft).sort();

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {keys.map((key) => (
          <Field key={key} id={`cfg-${key}`} label={key}>
            <Input
              value={draft[key] ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
            />
          </Field>
        ))}
      </div>

      {diffs.length > 0 && (
        <div className="rounded border border-border bg-surface-sunken p-2 text-xs">
          <p className="mb-1 font-medium text-text">Diff before save</p>
          <ul className="space-y-0.5 font-mono text-text-muted">
            {diffs.map((k) => (
              <li key={k}>
                {k}: {stringifyValue(values[k])} → {draft[k]}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={busy || diffs.length === 0} onClick={() => void save()}>
          {busy ? "Saving…" : "Save config"}
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => void reload()}>
          Reload
        </Button>
        {saved && <span className="text-sm text-success">{saved}</span>}
        {error && (
          <span role="alert" className="text-sm text-danger">
            {error}
          </span>
        )}
      </div>
    </div>
  );
}
