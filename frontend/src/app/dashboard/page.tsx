"use client";

import Link from "next/link";
import { useAccount } from "wagmi";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { QueryState } from "@/components/ui/data-state";
import { CountdownRing } from "@/components/countdown-ring";
import { IntervalBadge, STATE_META } from "@/components/interval-badge";
import { BalancesCard } from "@/components/balances-card";
import { GridStatusCard } from "@/components/grid-status-card";
import { ReputationGauge, TIER_META } from "@/components/reputation-gauge";
import { TradesTable } from "@/components/trades-table";
import { useAuth, useIsSignedIn } from "@/lib/auth";
import { useCurrentInterval, useReputation, useTrades } from "@/lib/queries";
import { formatSdr, paiseToInr } from "@/lib/format";

export default function DashboardPage() {
  const { address } = useAccount();
  const signedIn = useIsSignedIn(address);
  const me = useAuth((s) => s.me);
  const interval = useCurrentInterval();
  const reputation = useReputation(address);
  const trades = useTrades(signedIn, 8);

  const iv = interval.data;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Where the market is right now, and where you stand in it."
        actions={
          <Button variant="primary" asChild>
            <Link href="/trade">Place a position</Link>
          </Button>
        }
      />

      <div className="mb-3 grid grid-cols-2 gap-1 md:grid-cols-4">
        <Stat label="Interval" value={iv ? `#${iv.id}` : "—"} hint={iv ? STATE_META[iv.state].label : undefined} />
        <Stat label="Reference price" value={iv ? paiseToInr(iv.p_ref_paise ?? iv.prev_p_ref_paise) : "—"} unit="₹/kWh" live />
        <Stat label="Supply ÷ demand" value={formatSdr(iv?.sdr)} unit="SDR" />
        <Stat
          label="Your tier"
          value={reputation.data ? TIER_META[reputation.data.tier].label : address ? "…" : "—"}
          hint={reputation.data ? `score ${reputation.data.score.toFixed(2)}` : "connect a wallet"}
        />
      </div>

      <div className="grid gap-2 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Current interval" description="15-minute market cycle" action={iv && <IntervalBadge state={iv.state} />} />
          <QueryState query={interval} rows={3}>
            {(i) => (
              <CardBody className="flex flex-col items-center gap-2 text-center">
                <CountdownRing startsAt={i.starts_at} endsAt={i.ends_at} label="until next interval" />
                <p className="text-xs text-text-muted">{STATE_META[i.state].hint}</p>
                <dl className="grid w-full grid-cols-2 gap-1 text-xs">
                  <div className="rounded bg-surface-sunken px-2 py-1">
                    <dt className="text-text-muted">Commit closes</dt>
                    <dd className="num text-text">{new Date(i.commit_deadline).toLocaleTimeString()}</dd>
                  </div>
                  <div className="rounded bg-surface-sunken px-2 py-1">
                    <dt className="text-text-muted">Reveal closes</dt>
                    <dd className="num text-text">{new Date(i.reveal_deadline).toLocaleTimeString()}</dd>
                  </div>
                </dl>
              </CardBody>
            )}
          </QueryState>
        </Card>

        <div className="flex min-w-0 flex-col gap-2 lg:col-span-2">
          <BalancesCard />
          <Card>
            <CardHeader
              title="Reputation"
              description="Built from deliveries, reveals, honest reports and independence from collusion"
            />
            {!address ? (
              <CardBody className="text-sm text-text-muted">Connect a wallet to see your reputation.</CardBody>
            ) : (
              <QueryState query={reputation} rows={3}>
                {(r) => (
                  <CardBody className="grid gap-2 sm:grid-cols-2">
                    <ReputationGauge reputation={r} />
                    <dl className="grid grid-cols-2 gap-1 self-center text-xs">
                      {(
                        [
                          ["Delivery", r.components.delivery],
                          ["Reveal", r.components.reveal],
                          ["Honesty", r.components.honesty],
                          ["Collusion-free", r.components.collusion],
                        ] as const
                      ).map(([k, v]) => (
                        <div key={k} className="rounded bg-surface-sunken px-2 py-1">
                          <dt className="text-text-muted">{k}</dt>
                          <dd className="num text-base text-text">{v.toFixed(2)}</dd>
                        </div>
                      ))}
                      <div className="col-span-2 rounded bg-surface-sunken px-2 py-1">
                        <dt className="text-text-muted">Volume cap this interval</dt>
                        <dd className="num text-base text-text">{r.volume_cap_kwh} kWh</dd>
                      </div>
                    </dl>
                  </CardBody>
                )}
              </QueryState>
            )}
          </Card>
        </div>

        <Card className="lg:col-span-2">
          <CardHeader
            title={signedIn ? "Your last trades" : "Recent trades"}
            description={signedIn ? `Signed in as ${me?.participant?.display_name ?? me?.address}` : "Pseudonymous; connect and sign in to see yours"}
            action={
              <Button size="sm" variant="link" asChild>
                <Link href="/trade">All positions</Link>
              </Button>
            }
          />
          <QueryState
            query={trades}
            rows={5}
            empty={{
              when: (t) => t.length === 0,
              title: signedIn ? "No trades yet" : "No trades in this interval yet",
              hint: signedIn ? "Place a position during the commit window and it will appear here once cleared." : undefined,
              action: signedIn ? (
                <Button size="sm" asChild>
                  <Link href="/trade">Place a position</Link>
                </Button>
              ) : undefined,
            }}
          >
            {(t) => <TradesTable trades={t} mine={signedIn} compact />}
          </QueryState>
        </Card>

        <GridStatusCard />
      </div>
    </>
  );
}
