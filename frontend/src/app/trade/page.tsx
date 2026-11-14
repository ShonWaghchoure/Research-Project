"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAccount } from "wagmi";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardFooter, CardHeader, Stat } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Segmented } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { Empty, QueryState } from "@/components/ui/data-state";
import { Stepper, type Step } from "@/components/ui/stepper";
import { InfoTip } from "@/components/ui/tooltip";
import { IntervalBadge, STATE_META } from "@/components/interval-badge";
import { CountdownRing } from "@/components/countdown-ring";
import { TradesTable } from "@/components/trades-table";
import { TxStatusLine } from "@/components/tx-status";
import { api } from "@/lib/api/client";
import type { Position } from "@/lib/api/types";
import { useAuth, useIsSignedIn } from "@/lib/auth";
import { useSiwe } from "@/lib/siwe";
import { useChainAccount, useOnChainCommit } from "@/lib/chain";
import { contracts } from "@/lib/contracts";
import { computeCommitHash, randomSalt } from "@/lib/commit-hash";
import { formatInr, formatKwh, formatPrice, formatSdr, inrToPaise, kwhToWh, paiseToInr, paymentPaise } from "@/lib/format";
import { expectedPriceRange, DEFAULT_PRICING } from "@/lib/pricing";
import { queryKeys, useCurrentInterval, useMyPositions, useOrderbook, useReputation, useTrades } from "@/lib/queries";
import {
  amountSchema,
  positionSchema,
  type AmountForm,
  type AmountFormInput,
  type PositionForm,
  type PositionFormInput,
} from "@/lib/schemas";
import { useTx } from "@/lib/tx";

/** Seconds before the commit deadline after which new commits are refused. */
const COMMIT_SAFETY_SECONDS = 5;

function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export default function TradePage() {
  const { address } = useAccount();
  const signedIn = useIsSignedIn(address);
  const me = useAuth((s) => s.me);
  const interval = useCurrentInterval();
  const iv = interval.data;

  return (
    <>
      <PageHeader title="Trade" description="One net position per interval: buy or sell, never both." />

      <div className="mb-3 grid grid-cols-2 gap-1 md:grid-cols-4">
        <Stat label="Interval" value={iv ? `#${iv.id}` : "—"} hint={iv ? STATE_META[iv.state].label : undefined} />
        <Stat label="Reference price" value={iv ? paiseToInr(iv.p_ref_paise ?? iv.prev_p_ref_paise) : "—"} unit="₹/kWh" live />
        <Stat label="Supply ÷ demand" value={formatSdr(iv?.sdr)} unit="SDR" />
        <Stat label="Price band" value="3.00 – 8.00" unit="₹/kWh" hint="feed-in to retail" />
      </div>

      {!address ? (
        <Card>
          <Empty title="Connect a wallet to trade" hint="Use the Connect button in the top right. Demo accounts are available on the local chain." />
        </Card>
      ) : !signedIn ? (
        <SignInCard />
      ) : !me?.participant ? (
        <Card>
          <Empty
            title="Finish onboarding first"
            hint="Your wallet is signed in but has no participant profile yet."
            action={
              <Button variant="primary" asChild>
                <Link href="/onboarding">Go to onboarding</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-2 lg:grid-cols-3">
          <div className="flex min-w-0 flex-col gap-2 lg:col-span-2">
            <PositionCard interval={interval} />
            <EscrowCard />
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <Card>
              <CardHeader title="Window" action={iv && <IntervalBadge state={iv.state} />} />
              <QueryState query={interval} rows={2}>
                {(i) => (
                  <CardBody className="flex flex-col items-center gap-1 text-center">
                    <CountdownRing
                      startsAt={i.state === "COMMIT" || i.state === "OPEN" ? i.starts_at : i.commit_deadline}
                      endsAt={i.state === "COMMIT" || i.state === "OPEN" ? i.commit_deadline : i.state === "REVEAL" ? i.reveal_deadline : i.ends_at}
                      label={i.state === "COMMIT" || i.state === "OPEN" ? "to commit" : i.state === "REVEAL" ? "to reveal" : "to next interval"}
                      size={104}
                    />
                    <p className="text-xs text-text-muted">{STATE_META[i.state].hint}</p>
                  </CardBody>
                )}
              </QueryState>
            </Card>
            <MyPositionsCard />
          </div>
          <Card className="lg:col-span-3">
            <CardHeader title="Your trades" description="Settlement is authoritative; reconcile against this record, not notifications." />
            <MyTrades />
          </Card>
        </div>
      )}
    </>
  );
}

function SignInCard() {
  const { signIn, busy, error } = useSiwe();
  return (
    <Card>
      <CardHeader title="Sign in" description="Prove you control this wallet by signing a one-time message. No transaction, no gas." />
      <CardBody className="flex flex-col gap-1">
        <Button variant="primary" loading={busy} onClick={() => signIn().catch(() => undefined)} className="self-start">
          Sign in with Ethereum
        </Button>
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------

type Phase = "form" | "create" | "commit" | "await-reveal" | "reveal" | "done" | "failed";

function PositionCard({ interval }: { interval: ReturnType<typeof useCurrentInterval> }) {
  const { address } = useAccount();
  const iv = interval.data;
  const orderbook = useOrderbook();
  const reputation = useReputation(address);
  const chain = useChainAccount();
  const positions = useMyPositions();
  const qc = useQueryClient();
  const tx = useTx();

  const [phase, setPhase] = useState<Phase>("form");
  const [position, setPosition] = useState<Position | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const form = useForm<PositionFormInput, unknown, PositionForm>({
    resolver: zodResolver(positionSchema),
    defaultValues: { side: "buy", qty_kwh: 1, limit_price_inr: 5.5, deadline: "" },
    mode: "onChange",
  });
  const side = form.watch("side");
  const qty = Number(form.watch("qty_kwh"));
  const limit = Number(form.watch("limit_price_inr"));

  const qtyWh = kwhToWh(Number.isFinite(qty) ? qty : 0) ?? 0;
  const limitPaise = inrToPaise(Number.isFinite(limit) ? limit : 0) ?? 0;

  const range = useMemo(() => {
    if (!orderbook.data) return null;
    return expectedPriceRange(side, qtyWh, orderbook.data.supply_wh, orderbook.data.demand_wh, iv?.prev_p_ref_paise ?? iv?.p_ref_paise ?? null);
  }, [orderbook.data, side, qtyWh, iv]);

  // Grid-only comparison: buyers pay retail, sellers get feed-in.
  const gridPaise = side === "buy" ? paymentPaise(qtyWh, DEFAULT_PRICING.pRetPaise) : paymentPaise(qtyWh, DEFAULT_PRICING.pFitPaise);
  const p2pLow = range ? paymentPaise(qtyWh, range.lowPaise) : null;
  const p2pHigh = range ? paymentPaise(qtyWh, range.highPaise) : null;

  const neededEscrow = side === "buy" ? paymentPaise(qtyWh, limitPaise) : 0;
  const escrow = chain.data?.escrowPaise ?? 0n;
  const escrowShort = side === "buy" && BigInt(neededEscrow) > escrow ? BigInt(neededEscrow) - escrow : 0n;

  const volumeCapKwh = reputation.data?.volume_cap_kwh ?? null;
  const overCap = volumeCapKwh !== null && qty > volumeCapKwh;

  const existing = positions.data?.find((p) => p.interval_id === iv?.id) ?? null;
  // Leave time for the signature and mining before the on-chain deadline.
  const now = useNow(1000);
  const commitSecondsLeft = iv ? (new Date(iv.commit_deadline).getTime() - now) / 1000 : 0;
  const closingSoon = iv?.state === "COMMIT" && commitSecondsLeft <= COMMIT_SAFETY_SECONDS;
  const canCommit = iv?.state === "COMMIT" && !closingSoon;
  const suspended = reputation.data?.tier === "suspended" || chain.data?.suspended;

  // Resume a half-finished flow after a refresh or navigation. Whether the position was
  // committed is read from the contract, not from local state (which a refresh loses).
  const onChain = useOnChainCommit(existing?.interval_id);
  useEffect(() => {
    if (phase !== "form" || !existing || existing.revealed || onChain.isPending) return;
    const committed =
      !!onChain.commitHash && onChain.commitHash.toLowerCase() === existing.commit_hash.toLowerCase();
    setPosition({ ...existing, committed_tx: committed ? existing.committed_tx ?? "on-chain" : null });
    setPhase(committed ? "await-reveal" : "commit");
  }, [existing, phase, onChain.isPending, onChain.commitHash]);

  // Auto-reveal once the reveal window opens.
  useEffect(() => {
    if (phase === "await-reveal" && iv?.state === "REVEAL" && position) {
      setPhase("reveal");
      reveal.mutate(position);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, iv?.state, position?.id]);

  const create = useMutation({
    mutationFn: async (values: PositionForm) => {
      if (!iv || !address) throw new Error("No open interval.");
      const salt = randomSalt();
      const qty_wh = kwhToWh(values.qty_kwh)!;
      const limit_price_paise = inrToPaise(values.limit_price_inr)!;
      const deadline = values.deadline ? Math.floor(new Date(values.deadline).getTime() / 1000) : 0;
      const local = computeCommitHash({ intervalId: iv.id, participant: address, side: values.side, qtyWh: qty_wh, limitPricePaise: limit_price_paise, deadline, salt });
      const created = await api.positions.create({ interval_id: iv.id, side: values.side, qty_wh, limit_price_paise, deadline, salt });
      if (created.commit_hash.toLowerCase() !== local.toLowerCase())
        throw new Error("The server's commit hash differs from the one computed here. Not committing.");
      return created;
    },
    onSuccess: (p) => {
      setPosition(p);
      qc.invalidateQueries({ queryKey: queryKeys.positionsMine });
      setPhase("commit");
      commit.mutate(p);
    },
    onError: (e: Error) => {
      setFailure(e.message);
      setPhase("failed");
    },
  });

  const commit = useMutation({
    mutationFn: async (p: Position) => {
      const hash = await tx.run({ ...contracts.Settlement, functionName: "commitPosition", args: [BigInt(p.interval_id), p.commit_hash] });
      return hash;
    },
    onSuccess: (_hash, p) => {
      setPosition({ ...p, committed_tx: _hash });
      qc.invalidateQueries({ queryKey: queryKeys.positionsMine });
      setPhase("await-reveal");
    },
    onError: (e: Error) => {
      setFailure(e.message);
      setPhase("failed");
    },
  });

  const reveal = useMutation({
    mutationFn: async (p: Position) => api.positions.reveal(p.id, p.committed_tx ?? "0x"),
    onSuccess: (p) => {
      setPosition(p);
      qc.invalidateQueries({ queryKey: queryKeys.positionsMine });
      qc.invalidateQueries({ queryKey: queryKeys.orderbook });
      setPhase("done");
    },
    onError: (e: Error) => {
      setFailure(e.message);
      setPhase("failed");
    },
  });

  const reset = () => {
    setPhase("form");
    setPosition(null);
    setFailure(null);
    tx.reset();
  };

  const steps: Step[] = [
    {
      id: "create",
      title: "Seal the position",
      description: position ? (
        <span className="num font-mono">hash {position.commit_hash.slice(0, 10)}… · salt kept privately</span>
      ) : (
        "A random salt is generated here and the position is stored privately."
      ),
      status: phase === "create" ? "active" : position ? "done" : phase === "failed" && !position ? "failed" : "todo",
    },
    {
      id: "commit",
      title: "Commit on chain",
      description: <TxStatusLine tx={tx} className="mt-0.5" />,
      status: phase === "commit" ? "active" : position?.committed_tx ? "done" : phase === "failed" && position && !position.committed_tx ? "failed" : "todo",
    },
    {
      id: "reveal",
      title: "Reveal",
      description:
        phase === "await-reveal"
          ? "Waiting for the reveal window. This happens automatically; keep this page open or come back during reveal."
          : phase === "done"
            ? "Revealed and verified against your on-chain commit. The engine will price and match it at clearing."
            : "The position is sent in clear and checked against the hash on chain.",
      status: phase === "reveal" ? "active" : phase === "done" ? "done" : phase === "failed" && position?.committed_tx ? "failed" : "todo",
    },
  ];

  const onSubmit = form.handleSubmit((values) => {
    setFailure(null);
    setPhase("create");
    create.mutate(values);
  });

  if (phase !== "form") {
    return (
      <Card>
        <CardHeader
          title={
            position
              ? position.side === "buy"
                ? `Buy ${formatKwh(position.qty_wh)}, paying at most ${formatPrice(position.limit_price_paise)}`
                : `Sell ${formatKwh(position.qty_wh)}, receiving at least ${formatPrice(position.limit_price_paise)}`
              : "Submitting position"
          }
          description={position ? `Interval #${position.interval_id}` : undefined}
        />
        <CardBody>
          <Stepper steps={steps} />
          {failure && (
            <p role="alert" className="mt-2 text-xs text-danger">
              {failure}
            </p>
          )}
        </CardBody>
        <CardFooter>
          {phase === "commit" && position && !commit.isPending && tx.status !== "signing" && tx.status !== "pending" && (
            <Button
              variant="primary"
              disabled={!canCommit}
              onClick={() => {
                setFailure(null);
                commit.mutate(position);
              }}
            >
              Commit now
            </Button>
          )}
          {phase === "failed" && position && !position.committed_tx && (
            <Button variant="primary" onClick={() => { setFailure(null); setPhase("commit"); commit.mutate(position); }}>
              Retry commit
            </Button>
          )}
          {phase === "failed" && position?.committed_tx && (
            <Button variant="primary" onClick={() => { setFailure(null); setPhase("reveal"); reveal.mutate(position); }}>
              Retry reveal
            </Button>
          )}
          {phase === "await-reveal" && (
            <Button disabled={iv?.state !== "REVEAL"} onClick={() => position && reveal.mutate(position)}>
              Reveal now
            </Button>
          )}
          {(phase === "done" || phase === "failed") && <Button onClick={reset}>New position</Button>}
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="New position"
        description="Sealed with a hash until the reveal window, so nobody can trade against your bid."
        action={
          <InfoTip label="How the price is formed">
            The reference price comes from the supply-to-demand ratio of all revealed positions and is kept between the
            feed-in tariff (₹3.00) and the retail tariff (₹8.00). Your limit is the worst price you accept; you are only
            matched if the reference price is within it. Reputation affects matching order, never the price.
          </InfoTip>
        }
      />
      <form onSubmit={onSubmit} noValidate>
        <CardBody className="grid gap-2 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Segmented
              name="side"
              label="Side"
              value={side}
              onChange={(v) => form.setValue("side", v, { shouldValidate: true })}
              options={[
                { value: "buy", label: "Buy", description: "I need energy this interval" },
                { value: "sell", label: "Sell", description: "I have surplus to offer" },
              ]}
            />
          </div>
          <Field
            id="qty"
            label="Quantity"
            unit="kWh"
            error={form.formState.errors.qty_kwh?.message ?? (overCap ? `Above your volume cap of ${volumeCapKwh} kWh` : undefined)}
            help={volumeCapKwh !== null ? `Your cap this interval is ${volumeCapKwh} kWh` : undefined}
          >
            <Input type="number" step="0.001" min="0" inputMode="decimal" {...form.register("qty_kwh")} />
          </Field>
          <Field
            id="limit"
            label={side === "buy" ? "Maximum price" : "Minimum price"}
            unit="₹ per kWh"
            error={form.formState.errors.limit_price_inr?.message}
            help="Between ₹3.00 (feed-in) and ₹8.00 (retail)"
          >
            <Input type="number" step="0.01" min="3" max="8" inputMode="decimal" {...form.register("limit_price_inr")} />
          </Field>
          <Field id="deadline" label="Deadline" unit="optional" help="For EV charging: when the energy must have arrived." error={form.formState.errors.deadline?.message}>
            <Input type="datetime-local" {...form.register("deadline")} />
          </Field>

          <div className="rounded border border-border bg-surface-sunken px-2 py-2 text-xs sm:col-span-2">
            <div className="grid gap-1 sm:grid-cols-3">
              <div>
                <div className="text-text-muted">Expected clearing price</div>
                <div className="num text-base text-text">
                  {range ? (range.lowPaise === range.highPaise ? paiseToInr(range.lowPaise) : `${paiseToInr(range.lowPaise)} – ${paiseToInr(range.highPaise)}`) : "—"}{" "}
                  <span className="text-xs text-text-muted">₹/kWh</span>
                </div>
                <div className="text-text-faint">from the anonymised order book; a preview, not a quote</div>
              </div>
              <div>
                <div className="text-text-muted">{side === "buy" ? "Grid-only cost" : "Grid-only revenue"}</div>
                <div className="num text-base text-text">{formatInr(gridPaise)}</div>
                <div className="text-text-faint">{side === "buy" ? "at the retail tariff" : "at the feed-in tariff"}</div>
              </div>
              <div>
                <div className="text-text-muted">{side === "buy" ? "Peer-to-peer cost" : "Peer-to-peer revenue"}</div>
                <div className="num text-base text-text">
                  {p2pLow !== null && p2pHigh !== null ? (p2pLow === p2pHigh ? formatInr(p2pLow) : `${formatInr(p2pLow)} – ${formatInr(p2pHigh)}`) : "—"}
                </div>
                <div className="text-text-faint">
                  {p2pHigh !== null && gridPaise > 0
                    ? side === "buy"
                      ? `saves up to ${formatInr(Math.max(0, gridPaise - p2pLow!))}`
                      : `earns up to ${formatInr(Math.max(0, p2pHigh - gridPaise))} more`
                    : ""}
                </div>
              </div>
            </div>
          </div>

          {side === "buy" && escrowShort > 0n && (
            <div role="status" className="flex flex-wrap items-center justify-between gap-1 rounded border border-warning/40 bg-warning-soft px-2 py-1 text-xs sm:col-span-2">
              <span className="text-text">
                Escrow is short by <span className="num font-medium">{formatInr(escrowShort)}</span> for this bid ({formatInr(neededEscrow)} needed, {formatInr(escrow)} held).
              </span>
              <Button size="sm" asChild>
                <a href="#escrow">Deposit</a>
              </Button>
            </div>
          )}
        </CardBody>
        <CardFooter className="justify-between">
          <span className="text-xs text-text-muted">
            {suspended
              ? "This account is suspended and cannot trade."
              : existing
                ? "You already have a position in this interval."
                : closingSoon
                  ? "Commit window is closing; too little time left to sign and confirm. Wait for the next interval."
                  : canCommit
                  ? "Commit window is open."
                  : iv
                    ? `Commit window is ${iv.state === "OPEN" ? "about to open" : "closed"}; the next one opens with the next interval.`
                    : ""}
          </span>
          <Button
            type="submit"
            variant="primary"
            disabled={!canCommit || !!existing || !!suspended || overCap || escrowShort > 0n || !form.formState.isValid}
            data-testid="submit-position"
          >
            {side === "buy" ? "Commit buy" : "Commit sell"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------

function MyPositionsCard() {
  const positions = useMyPositions();
  const iv = useCurrentInterval().data;
  return (
    <Card>
      <CardHeader title="Your positions" description="Most recent first" />
      <QueryState query={positions} rows={3} empty={{ when: (p) => p.length === 0, title: "No positions yet" }}>
        {(ps) => (
          <ul className="divide-y divide-border">
            {[...ps].sort((a, b) => b.interval_id - a.interval_id).slice(0, 6).map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-1 px-3 py-1 text-xs">
                <span>
                  <span className="num font-medium text-text">#{p.interval_id}</span>{" "}
                  <span className="text-text-muted">
                    {p.side} {formatKwh(p.qty_wh)} at {paiseToInr(p.limit_price_paise)} ₹/kWh
                  </span>
                </span>
                <Badge tone={p.revealed ? "success" : iv?.id === p.interval_id ? "accent" : "warning"}>
                  {p.revealed ? "Revealed" : iv?.id === p.interval_id ? "Sealed" : "Not revealed"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Card>
  );
}

function MyTrades() {
  const trades = useTrades(true, 20);
  return (
    <QueryState query={trades} rows={4} empty={{ when: (t) => t.length === 0, title: "No trades yet", hint: "Trades appear here after clearing." }}>
      {(t) => <TradesTable trades={t} mine />}
    </QueryState>
  );
}

// ---------------------------------------------------------------------------

function EscrowCard() {
  const chain = useChainAccount();
  const tx = useTx();
  const [mode, setMode] = useState<"deposit" | "withdraw">("deposit");
  const form = useForm<AmountFormInput, unknown, AmountForm>({ resolver: zodResolver(amountSchema), defaultValues: { amount_inr: 50 } });

  const run = useMutation({
    mutationFn: async ({ amount_inr }: AmountForm) => {
      const paise = BigInt(inrToPaise(amount_inr)!);
      if (mode === "deposit") {
        await tx.run({ ...contracts.MockINR, functionName: "approve", args: [contracts.Settlement.address, paise] });
        await tx.run({ ...contracts.Settlement, functionName: "deposit", args: [paise] });
      } else {
        await tx.run({ ...contracts.Settlement, functionName: "withdrawEscrow", args: [paise] });
      }
    },
    onSuccess: () => chain.refetch(),
  });

  return (
    <Card id="escrow">
      <CardHeader
        title="Escrow"
        description="Buyers fund escrow before committing. Unused escrow can be withdrawn at any time."
        action={
          <span className="num text-sm text-text">
            {chain.data ? formatInr(chain.data.escrowPaise) : "—"} <span className="text-xs text-text-muted">held</span>
          </span>
        }
      />
      <form onSubmit={form.handleSubmit((v) => run.mutate(v))} noValidate>
        <CardBody className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
          <Field id="escrow-amount" label={mode === "deposit" ? "Amount to deposit" : "Amount to withdraw"} unit="₹" error={form.formState.errors.amount_inr?.message}
            help={chain.data ? `Wallet ${formatInr(chain.data.balancePaise)}` : undefined}>
            <Input type="number" step="0.01" min="0" inputMode="decimal" {...form.register("amount_inr")} />
          </Field>
          <div className="flex gap-1">
            <Button type="submit" variant={mode === "deposit" ? "primary" : "secondary"} loading={run.isPending && mode === "deposit"} onClick={() => setMode("deposit")} data-testid="escrow-deposit">
              Deposit
            </Button>
            <Button type="submit" variant={mode === "withdraw" ? "primary" : "secondary"} loading={run.isPending && mode === "withdraw"} onClick={() => setMode("withdraw")}>
              Withdraw
            </Button>
          </div>
          {tx.status !== "idle" && (
            <div className="sm:col-span-2">
              <TxStatusLine tx={tx} />
            </div>
          )}
        </CardBody>
      </form>
    </Card>
  );
}

