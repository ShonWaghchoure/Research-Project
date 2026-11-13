"use client";

import { useEffect, useRef, useState } from "react";
import { useAccount } from "wagmi";
import { PageHeader } from "@/components/page-header";
import { ReputationGauge, TierBadge } from "@/components/reputation-gauge";
import { ComponentRadar } from "@/components/reputation/component-radar";
import { ProofVerifier } from "@/components/reputation/proof-verifier";
import { ScoreHistoryChart } from "@/components/reputation/score-history-chart";
import { TierLadder } from "@/components/reputation/tier-ladder";
import { WhatIfPanel } from "@/components/reputation/what-if-panel";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Empty, QueryState } from "@/components/ui/data-state";
import { useReputation, useReputationHistory } from "@/lib/queries";
import type { Tier } from "@/lib/api/types";

export default function ReputationPage() {
  const { address } = useAccount();
  const reputation = useReputation(address);
  const history = useReputationHistory(address);
  const [celebration, setCelebration] = useState<Tier | null>(null);
  const prevTier = useRef<Tier | null>(null);

  useEffect(() => {
    const tier = reputation.data?.tier;
    if (!tier) return;
    if (prevTier.current && prevTier.current !== tier && (tier === "trusted" || tier === "standard")) {
      setCelebration(tier);
      const t = setTimeout(() => setCelebration(null), 3200);
      return () => clearTimeout(t);
    }
    prevTier.current = tier;
  }, [reputation.data?.tier]);

  return (
    <>
      <PageHeader
        title="Reputation"
        description="Score history, the four evidence components, the tier ladder, a what-if path to Trusted, and on-chain proof verification."
      />

      {celebration && (
        <div
          role="status"
          className="mb-2 animate-fade-in rounded border border-success/30 bg-success-soft px-3 py-2 text-sm text-success"
        >
          Tier moved to <TierBadge tier={celebration} className="align-middle" />. Quiet recognition — reputation never changes the price.
        </div>
      )}

      {!address ? (
        <Card>
          <Empty
            title="Connect a wallet"
            hint="Reputation is per address. Connect on the local chain to see your score, history and Merkle proof."
          />
        </Card>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-1 md:grid-cols-4">
            <Stat
              label="Score"
              value={reputation.data ? reputation.data.score.toFixed(3) : "—"}
              hint="Lower confidence bound of the Beta posterior"
            />
            <Stat
              label="Tier"
              value={reputation.data ? reputation.data.tier : "—"}
            />
            <Stat
              label="Evidence"
              value={reputation.data ? String(reputation.data.evidence_count) : "—"}
              hint="Trusted needs 100"
            />
            <Stat
              label="Volume cap"
              value={reputation.data ? reputation.data.volume_cap_kwh.toFixed(1) : "—"}
              unit="kWh"
            />
          </div>

          <div className="grid gap-2 lg:grid-cols-3">
            <Card>
              <CardHeader title="Current score" description="Half-ring with tier thresholds" />
              <QueryState query={reputation} rows={3}>
                {(r) => (
                  <CardBody className="flex justify-center">
                    <ReputationGauge reputation={r} />
                  </CardBody>
                )}
              </QueryState>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader title="Score history" description="After each metered interval" />
              <QueryState
                query={history}
                rows={4}
                empty={{
                  when: (d) => d.history.length === 0,
                  title: "No history yet",
                  hint: "History appears once an interval reaches METERED and your address is in the reputation tree.",
                }}
              >
                {(d) => (
                  <CardBody>
                    <ScoreHistoryChart history={d.history} />
                  </CardBody>
                )}
              </QueryState>
            </Card>
          </div>

          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            <Card>
              <CardHeader title="Components" description="Delivery, reveal, honesty, collusion-free" />
              <QueryState query={reputation} rows={4}>
                {(r) => (
                  <CardBody>
                    <ComponentRadar components={r.components} />
                  </CardBody>
                )}
              </QueryState>
            </Card>

            <Card>
              <CardHeader title="Tier ladder" description="Rules that gate matching and volume" />
              <CardBody>
                <TierLadder current={reputation.data?.tier} />
              </CardBody>
            </Card>
          </div>

          <div className="mt-2 grid gap-2 lg:grid-cols-2">
            <Card>
              <CardHeader title="What-if" description="How many intervals to Trusted" />
              <QueryState query={reputation} rows={3}>
                {(r) => (
                  <CardBody>
                    <WhatIfPanel reputation={r} />
                  </CardBody>
                )}
              </QueryState>
            </Card>

            <Card>
              <CardHeader title="Proof verifier" description="Merkle leaf against ReputationAnchor" />
              <CardBody>
                <ProofVerifier address={address} history={history.data?.history ?? []} />
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
