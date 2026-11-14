"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api/client";
import type { AuditLogOut } from "@/lib/api/types";

export function AuditLogTable() {
  const [rows, setRows] = useState<AuditLogOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void api.admin
      .auditLog(100)
      .then(setRows)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to load audit log"),
      );
  }, []);

  if (error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {error}
      </p>
    );
  }
  if (!rows.length) {
    return <p className="text-sm text-text-muted">No admin actions logged yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] text-left text-xs">
        <thead className="text-text-muted">
          <tr className="border-b border-border">
            <th className="py-1 pr-2 font-medium">When</th>
            <th className="py-1 pr-2 font-medium">Actor</th>
            <th className="py-1 pr-2 font-medium">Action</th>
            <th className="py-1 pr-2 font-medium">Resource</th>
            <th className="py-1 font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-border/60 align-top">
              <td className="num whitespace-nowrap py-1 pr-2">
                {new Date(r.created_at).toLocaleString()}
              </td>
              <td className="num py-1 pr-2">{r.actor_user_id ?? "—"}</td>
              <td className="py-1 pr-2 font-mono">{r.action}</td>
              <td className="py-1 pr-2">
                {r.resource_type}
                {r.resource_id ? `:${r.resource_id}` : ""}
              </td>
              <td className="max-w-[20rem] truncate py-1 font-mono text-text-muted" title={JSON.stringify(r.after)}>
                {r.after ? JSON.stringify(r.after) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
