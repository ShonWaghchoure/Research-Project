"use client";

import { useState } from "react";
import { AuditLogTable } from "@/components/admin/audit-log-table";
import { ConfigEditor } from "@/components/admin/config-editor";
import { FlagQueue } from "@/components/admin/flag-queue";
import { SimControls } from "@/components/admin/sim-controls";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Segmented } from "@/components/ui/field";
import { useIsAdmin } from "@/lib/auth";

type Tab = "config" | "flags" | "simulation" | "audit";

export default function AdminPage() {
  const isAdmin = useIsAdmin();
  const [tab, setTab] = useState<Tab>("config");

  if (!isAdmin) {
    return (
      <>
        <PageHeader title="Admin" description="Operators only." />
        <p role="status" className="rounded border border-warning bg-warning-soft px-2 py-2 text-sm text-text">
          Sign in with an admin wallet to open the console. Non-admin sessions cannot call admin APIs.
        </p>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Admin"
        description="Market parameters, detection flags, live simulation controls, and the admin audit log."
        actions={
          <Segmented
            name="admin-tab"
            label="Admin section"
            value={tab}
            onChange={(v) => setTab(v)}
            options={[
              { value: "config", label: "Parameters" },
              { value: "flags", label: "Flags" },
              { value: "simulation", label: "Simulation" },
              { value: "audit", label: "Audit log" },
            ]}
          />
        }
      />

      {tab === "config" && (
        <Card>
          <CardHeader
            title="Market parameters"
            description="Changes are validated server-side and written to the config table with an audit log entry. Review the diff before saving."
          />
          <CardBody>
            <ConfigEditor />
          </CardBody>
        </Card>
      )}

      {tab === "flags" && (
        <Card>
          <CardHeader
            title="Flag queue"
            description="Detection never auto-bans. Resolve or dismiss each flag after review."
          />
          <CardBody>
            <FlagQueue />
          </CardBody>
        </Card>
      )}

      {tab === "simulation" && (
        <Card>
          <CardHeader
            title="Live simulation"
            description="Start/stop the clock tick and override interval length for demos. Process-local; not persisted."
          />
          <CardBody>
            <SimControls />
          </CardBody>
        </Card>
      )}

      {tab === "audit" && (
        <Card>
          <CardHeader title="Admin audit log" description="Recent privileged actions." />
          <CardBody>
            <AuditLogTable />
          </CardBody>
        </Card>
      )}
    </>
  );
}
