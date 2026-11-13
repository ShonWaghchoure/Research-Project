"use client";

import { useAccount } from "wagmi";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryState } from "@/components/ui/data-state";
import { useHealth } from "@/lib/queries";
import { API_URL, WS_URL } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { contracts } from "@/lib/contracts";
import { CHAIN_ID, RPC_URL } from "@/lib/wagmi";

function Row({ label, value, ok }: { label: string; value: React.ReactNode; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border py-1 text-sm last:border-0">
      <span className="shrink-0 text-text-muted">{label}</span>
      <span className="num flex min-w-0 items-center gap-1 break-all text-right font-mono text-xs text-text">
        {ok !== undefined && <Badge tone={ok ? "success" : "danger"}>{ok ? "ok" : "down"}</Badge>}
        {value}
      </span>
    </div>
  );
}

/** Phase 6 health demo, kept as a plain status page. */
export default function StatusPage() {
  const health = useHealth();
  const { address, chainId, connector } = useAccount();
  const { token, role, me } = useAuth();

  return (
    <>
      <PageHeader
        title="System status"
        description="Backend, chain and session details for operators and developers."
        actions={
          <Button size="sm" asChild>
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
              API docs
            </a>
          </Button>
        }
      />
      <div className="grid gap-2 md:grid-cols-2">
        <Card>
          <CardHeader title="Backend" description={API_URL} />
          <QueryState query={health} rows={4}>
            {(h) => (
              <CardBody>
                <Row label="Status" value={h.status} ok={h.status === "ok"} />
                <Row label="PostgreSQL" value={h.postgres} ok={h.postgres === "ok"} />
                <Row label="Redis" value={h.redis} ok={h.redis === "ok"} />
                <Row label="Chain RPC" value={h.chain_rpc} ok={h.chain_rpc === "ok"} />
                <Row label="Block" value={h.block_number ?? "—"} />
                <Row label="Chain id" value={h.chain_id} />
                <Row label="WebSocket" value={WS_URL} />
              </CardBody>
            )}
          </QueryState>
        </Card>
        <Card>
          <CardHeader title="Session" />
          <CardBody>
            <Row label="Wallet" value={address ?? "not connected"} />
            <Row label="Connector" value={connector?.name ?? "—"} />
            <Row label="Network" value={chainId ?? "—"} ok={chainId === undefined ? undefined : chainId === CHAIN_ID} />
            <Row label="Signed in" value={token ? `${role} · ${me?.participant?.display_name ?? "no profile"}` : "no"} />
          </CardBody>
        </Card>
        <Card className="md:col-span-2">
          <CardHeader title="Contracts" description={`${RPC_URL} · chain ${CHAIN_ID}`} />
          <CardBody>
            {Object.entries(contracts).map(([name, c]) => (
              <Row key={name} label={name} value={c.address} />
            ))}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
