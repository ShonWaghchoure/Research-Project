"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/field";
import { api, ApiError } from "@/lib/api/client";
import type { FlagOut } from "@/lib/api/types";

type Filter = "open" | "resolved" | "dismissed" | "";

export function FlagQueue() {
  const [status, setStatus] = useState<Filter>("open");
  const [flags, setFlags] = useState<FlagOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = await api.admin.flags.list(status || "open");
      setFlags(rows);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load flags");
    }
  }, [status]);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = async (id: number, next: "resolved" | "dismissed") => {
    setBusyId(id);
    setError(null);
    try {
      await api.admin.flags.resolve(id, { status: next });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Resolve failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-2">
      <Segmented
        name="flag-status"
        label="Flag status"
        value={status || "open"}
        onChange={(v) => setStatus(v as Filter)}
        options={[
          { value: "open", label: "Open" },
          { value: "resolved", label: "Resolved" },
          { value: "dismissed", label: "Dismissed" },
        ]}
      />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {!flags.length ? (
        <p className="text-sm text-text-muted">No flags in this queue.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-left text-xs">
            <thead className="text-text-muted">
              <tr className="border-b border-border">
                <th className="py-1 pr-2 font-medium">Id</th>
                <th className="py-1 pr-2 font-medium">Kind</th>
                <th className="py-1 pr-2 font-medium">Severity</th>
                <th className="py-1 pr-2 font-medium">Participant</th>
                <th className="py-1 pr-2 font-medium">Interval</th>
                <th className="py-1 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {flags.map((f) => (
                <tr key={f.id} className="border-b border-border/60">
                  <td className="num py-1 pr-2">{f.id}</td>
                  <td className="py-1 pr-2">{f.kind}</td>
                  <td className="py-1 pr-2">
                    <Badge
                      tone={
                        f.severity === "high"
                          ? "danger"
                          : f.severity === "medium"
                            ? "warning"
                            : "neutral"
                      }
                    >
                      {f.severity}
                    </Badge>
                  </td>
                  <td className="num py-1 pr-2">{f.participant_id ?? "—"}</td>
                  <td className="num py-1 pr-2">{f.interval_id ?? "—"}</td>
                  <td className="py-1">
                    {f.status === "open" ? (
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          disabled={busyId === f.id}
                          onClick={() => void resolve(f.id, "resolved")}
                        >
                          Resolve
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busyId === f.id}
                          onClick={() => void resolve(f.id, "dismissed")}
                        >
                          Dismiss
                        </Button>
                      </div>
                    ) : (
                      <span className="text-text-muted">{f.status}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
