"use client";

import { useState } from "react";
import { ExplorerLinks } from "@/components/audit/explorer-links";
import { HashCompare } from "@/components/audit/hash-compare";
import { MerkleViewer } from "@/components/audit/merkle-viewer";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { api, ApiError } from "@/lib/api/client";
import type { AuditReport, AuditRerunResponse } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";

export default function AuditPage() {
  const role = useAuth((s) => s.role);
  const canRerun = role === "admin" || role === "operator";
  const [intervalId, setIntervalId] = useState("");
  const [report, setReport] = useState<AuditReport | null>(null);
  const [rerun, setRerun] = useState<AuditRerunResponse | null>(null);
  const [busy, setBusy] = useState<"load" | "rerun" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const id = Number(intervalId);
    if (!Number.isInteger(id) || id <= 0) {
      setError("Enter a positive interval id.");
      return;
    }
    setError(null);
    setRerun(null);
    setBusy("load");
    try {
      const data = await api.audit.get(id);
      setReport(data);
    } catch (err) {
      setReport(null);
      setError(err instanceof ApiError ? err.detail : "Could not load audit report.");
    } finally {
      setBusy(null);
    }
  };

  const runRerun = async () => {
    if (!report) return;
    setError(null);
    setBusy("rerun");
    try {
      const data = await api.audit.rerun(report.interval_id);
      setRerun(data);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.status === 403
            ? "Operator or admin sign-in required to re-run clearing."
            : err.detail
          : "Re-run failed.",
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Audit"
        description="Inspect published inputs and results for an interval, compare hashes, and re-run clearing deterministically."
      />

      <Card className="mb-3">
        <CardHeader title="Interval" description="GET /audit/{id} is public. Re-run requires operator or admin." />
        <CardBody className="flex flex-wrap items-end gap-2">
          <Field id="audit-interval" label="Interval id" className="w-40">
            <Input
              type="number"
              min={1}
              value={intervalId}
              onChange={(e) => setIntervalId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void load();
              }}
            />
          </Field>
          <Button disabled={busy !== null} onClick={() => void load()}>
            {busy === "load" ? "Loading…" : "Load report"}
          </Button>
          <Button
            variant="secondary"
            disabled={!report || !canRerun || busy !== null}
            onClick={() => void runRerun()}
          >
            {busy === "rerun" ? "Re-running…" : "Re-run clearing"}
          </Button>
          {!canRerun && (
            <p className="w-full text-xs text-text-muted">
              Sign in as operator or admin to re-run the engine.
            </p>
          )}
          {error && (
            <p role="alert" className="w-full text-sm text-danger">
              {error}
            </p>
          )}
        </CardBody>
      </Card>

      {report && (
        <>
          <div className="mb-3 grid gap-3 lg:grid-cols-2">
            <HashCompare title="Input root" triple={rerun?.input_root ?? report.input_root} />
            <HashCompare title="Result hash" triple={rerun?.result_hash ?? report.result_hash} />
          </div>

          {rerun && (
            <Card className="mb-3">
              <CardHeader
                title={rerun.match ? "Re-run matches stored hashes" : "Re-run diverged"}
                description={`Stored engine ${rerun.engine_version_stored ?? "—"} · current ${rerun.engine_version_now}`}
              />
              <CardBody>
                {rerun.note ? (
                  <p className="text-sm text-warning">{rerun.note}</p>
                ) : (
                  <p className="text-sm text-text-muted">
                    Deterministic re-clear produced the same input root and result hash.
                  </p>
                )}
              </CardBody>
            </Card>
          )}

          <Card className="mb-3">
            <CardHeader
              title="Merkle leaves"
              description={`${report.merkle_leaves.length} revealed positions · state ${report.state}`}
            />
            <CardBody>
              <MerkleViewer leaves={report.merkle_leaves} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Explorer" />
            <CardBody>
              <ExplorerLinks explorer={report.explorer} />
            </CardBody>
          </Card>
        </>
      )}
    </>
  );
}
