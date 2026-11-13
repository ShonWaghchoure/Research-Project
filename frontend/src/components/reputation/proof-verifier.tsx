"use client";

import { useState } from "react";
import { usePublicClient } from "wagmi";
import { CheckCircle2, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api/client";
import type { ReputationHistoryPoint } from "@/lib/api/types";
import { contracts } from "@/lib/contracts";

type VerifyState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ok"; intervalId: number; root: string }
  | { status: "fail"; message: string };

/** Fetch a Merkle proof and verify it against ReputationAnchor on chain. */
export function ProofVerifier({
  address,
  history,
}: {
  address?: string | null;
  history: ReputationHistoryPoint[];
}) {
  const client = usePublicClient();
  const [state, setState] = useState<VerifyState>({ status: "idle" });
  const latest = history.length ? history[history.length - 1] : null;

  async function verify() {
    if (!address || !latest) {
      setState({ status: "fail", message: "No anchored score yet for this wallet." });
      return;
    }
    setState({ status: "loading" });
    try {
      const proof = await api.reputationProof(address, latest.interval_id);
      if (!client) {
        setState({
          status: "fail",
          message: "No chain client. Connect a wallet on the local Hardhat network.",
        });
        return;
      }
      const ok = await client.readContract({
        address: contracts.ReputationAnchor.address,
        abi: contracts.ReputationAnchor.abi,
        functionName: "verifyScore",
        args: [
          BigInt(proof.interval_id),
          proof.address as `0x${string}`,
          proof.score_bp,
          proof.evidence_count,
          proof.proof,
        ],
      });
      if (ok) setState({ status: "ok", intervalId: proof.interval_id, root: proof.root });
      else setState({ status: "fail", message: "On-chain verifyScore returned false for this leaf." });
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message.split("\n")[0]
            : "Verification failed";
      setState({ status: "fail", message: msg });
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-text-muted">
        After an interval is metered, the operator posts a Merkle root of reputation leaves to ReputationAnchor.
        This checks your leaf against that root on chain.
      </p>
      <div className="flex flex-wrap items-center gap-1">
        <Button
          variant="primary"
          size="sm"
          onClick={verify}
          loading={state.status === "loading"}
          disabled={!address || !latest}
        >
          <ShieldCheck className="h-2 w-2" aria-hidden />
          Verify on chain
        </Button>
        {latest && (
          <span className="text-xs text-text-muted">
            Latest leaf: interval <span className="num text-text">#{latest.interval_id}</span>, score{" "}
            <span className="num text-text">{(latest.score_bp / 100).toFixed(2)}</span>%
          </span>
        )}
      </div>
      {state.status === "ok" && (
        <div role="status" className="flex items-start gap-1 rounded border border-success/30 bg-success-soft px-2 py-1.5 text-sm text-success">
          <CheckCircle2 className="mt-0.5 h-2 w-2 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">Proof verified</p>
            <p className="text-xs">
              Interval #{state.intervalId} matches the on-chain root.
            </p>
            <Badge tone="success" className="mt-1 font-mono text-[10px]">
              {state.root.slice(0, 10)}…{state.root.slice(-6)}
            </Badge>
          </div>
        </div>
      )}
      {state.status === "fail" && (
        <div role="alert" className="flex items-start gap-1 rounded border border-warning/30 bg-warning-soft px-2 py-1.5 text-sm text-warning">
          <ShieldAlert className="mt-0.5 h-2 w-2 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">Could not verify</p>
            <p className="text-xs text-text-muted">{state.message}</p>
          </div>
        </div>
      )}
      {!address && <p className="text-xs text-text-muted">Connect a wallet to verify your own score.</p>}
      {address && !latest && (
        <p className="text-xs text-text-muted">
          No history yet. Wait until an interval reaches METERED (demo bots are anchored every interval).
        </p>
      )}
    </div>
  );
}
