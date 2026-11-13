"use client";

import Link from "next/link";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loading, ErrorState } from "@/components/ui/data-state";
import { Badge } from "@/components/ui/badge";
import { useChainAccount } from "@/lib/chain";
import { formatInr } from "@/lib/format";
import { chainParams } from "@/lib/contracts";

/** Wallet balance, escrow and stake, read directly from the contracts. */
export function BalancesCard() {
  const q = useChainAccount();
  return (
    <Card>
      <CardHeader
        title="Balance and escrow"
        description="Test INR (MockINR), 2 decimals"
        action={
          <Button size="sm" variant="link" asChild>
            <Link href="/trade#escrow">Manage escrow</Link>
          </Button>
        }
      />
      {!q.address ? (
        <CardBody className="text-sm text-text-muted">Connect a wallet to see balances.</CardBody>
      ) : q.isPending ? (
        <Loading rows={3} />
      ) : q.isError || !q.data ? (
        <ErrorState message="Could not read the contracts. Is the local chain running?" onRetry={() => q.refetch()} />
      ) : (
        <CardBody>
          <dl className="grid grid-cols-3 gap-1">
            <div>
              <dt className="text-xs text-text-muted">Wallet</dt>
              <dd className="num text-lg font-medium text-text">{formatInr(q.data.balancePaise)}</dd>
            </div>
            <div>
              <dt className="text-xs text-text-muted">Escrow</dt>
              <dd className="num text-lg font-medium text-text">{formatInr(q.data.escrowPaise)}</dd>
            </div>
            <div>
              <dt className="text-xs text-text-muted">Stake</dt>
              <dd className="num text-lg font-medium text-text">{formatInr(q.data.stakePaise)}</dd>
            </div>
          </dl>
          <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-text-muted">
            {q.data.registered ? (
              <Badge tone="success">Registered</Badge>
            ) : (
              <>
                <Badge tone="warning">Not registered</Badge>
                <Link href="/onboarding" className="text-accent underline-offset-2 hover:underline">
                  Finish onboarding
                </Link>
              </>
            )}
            {q.data.suspended && <Badge tone="danger">Suspended</Badge>}
            <span>Minimum stake {formatInr(chainParams.minStakePaise)}</span>
          </div>
        </CardBody>
      )}
    </Card>
  );
}
