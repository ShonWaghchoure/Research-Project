"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useAccount, useConnect } from "wagmi";
import { useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Segmented, Select } from "@/components/ui/field";
import { Stepper, type Step, type StepStatus } from "@/components/ui/stepper";
import { TxStatusLine } from "@/components/tx-status";
import { api } from "@/lib/api/client";
import { useAuth, useIsSignedIn } from "@/lib/auth";
import { useSiwe } from "@/lib/siwe";
import { useChainAccount } from "@/lib/chain";
import { chainParams, contracts } from "@/lib/contracts";
import { demoMeterKeyHash } from "@/lib/meter-key";
import { formatInr } from "@/lib/format";
import { participantSchema, type ParticipantForm, type ParticipantFormInput } from "@/lib/schemas";
import { useTx } from "@/lib/tx";
import { CHAIN_ID, DEMO_WALLET_ENABLED } from "@/lib/wagmi";
import { cn } from "@/lib/utils";

/** Feeder nodes from the Phase 2 fixture (n0 is the transformer and takes no participants). */
const NODES = ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "n10", "n11", "n12"];

const STEP_IDS = ["connect", "signin", "profile", "faucet", "register"] as const;
type StepId = (typeof STEP_IDS)[number];

export default function OnboardingPage() {
  const router = useRouter();
  const { address, isConnected } = useAccount();
  const signedIn = useIsSignedIn(address);
  const me = useAuth((s) => s.me);
  const refreshMe = useAuth((s) => s.refreshMe);
  const chain = useChainAccount();

  useEffect(() => {
    if (signedIn && !me) refreshMe();
  }, [signedIn, me, refreshMe]);

  const hasProfile = !!me?.participant;
  // Enough to reach the minimum stake (wallet + already staked), not merely "any tokens":
  // a wallet holding 1 paisa used to skip the faucet and then fail at staking.
  const hasTokens = (chain.data?.balancePaise ?? 0n) + (chain.data?.stakePaise ?? 0n) >= chainParams.minStakePaise;
  const registered = chain.data?.registered ?? false;

  const current: StepId = !isConnected ? "connect" : !signedIn ? "signin" : !hasProfile ? "profile" : !hasTokens ? "faucet" : !registered ? "register" : "register";
  const complete = isConnected && signedIn && hasProfile && registered;

  const status = (id: StepId): StepStatus => {
    if (complete) return "done";
    const i = STEP_IDS.indexOf(id);
    const c = STEP_IDS.indexOf(current);
    return i < c ? "done" : i === c ? "active" : "todo";
  };

  const steps: Step[] = [
    { id: "connect", title: "Connect a wallet", status: status("connect") },
    { id: "signin", title: "Sign in with Ethereum", status: status("signin") },
    { id: "profile", title: "Describe your home", status: status("profile") },
    { id: "faucet", title: "Get test INR", status: status("faucet") },
    { id: "register", title: "Stake and register", status: status("register") },
  ];

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Onboarding" description="Five short steps. Each is skipped automatically if it is already done." />
      <div className="grid gap-2 md:grid-cols-[220px_1fr]">
        <Card>
          <CardBody>
            <Stepper steps={steps} />
          </CardBody>
        </Card>
        <div>
          {complete ? (
            <Card>
              <CardHeader title="You are set up" description="Your wallet is registered on chain and has a participant profile." />
              <CardFooter>
                <Button variant="primary" onClick={() => router.push("/trade")} data-testid="go-trade">
                  Go to trade
                </Button>
                <Button onClick={() => router.push("/dashboard")}>Dashboard</Button>
              </CardFooter>
            </Card>
          ) : current === "connect" ? (
            <ConnectStep />
          ) : current === "signin" ? (
            <SignInStep />
          ) : current === "profile" ? (
            <ProfileStep />
          ) : current === "faucet" ? (
            <FaucetStep onDone={() => chain.refetch()} />
          ) : (
            <RegisterStep onDone={() => chain.refetch()} />
          )}
        </div>
      </div>
    </div>
  );
}

function ConnectStep() {
  const { connectors, connect, isPending, error } = useConnect();
  const injected = connectors.find((c) => c.id === "injected");
  const demos = connectors.filter((c) => c.id.startsWith("demo-"));
  return (
    <Card>
      <CardHeader title="Connect a wallet" description="Your address is your market identity. Connecting sends nothing." />
      <CardBody className="flex flex-col gap-1">
        {injected && (
          <Button variant="primary" size="lg" loading={isPending} onClick={() => connect({ connector: injected, chainId: CHAIN_ID })} className="self-start">
            Browser wallet
          </Button>
        )}
        {DEMO_WALLET_ENABLED && demos.length > 0 && (
          <>
            <p className="mt-1 text-xs text-text-muted">Or use a local demo account (Hardhat test accounts, local chain only):</p>
            <div className="flex flex-wrap gap-1">
              {demos.map((c) => (
                <Button key={c.id} loading={isPending} data-testid={c.id} onClick={() => connect({ connector: c, chainId: CHAIN_ID })}>
                  {c.name}
                </Button>
              ))}
            </div>
          </>
        )}
        {error && (
          <p role="alert" className="text-xs text-danger">
            {error.message.split("\n")[0]}
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function SignInStep() {
  const { signIn, busy, error } = useSiwe();
  return (
    <Card>
      <CardHeader title="Sign in with Ethereum" description="Sign a one-time message to prove you control the wallet. No gas." />
      <CardBody className="flex flex-col gap-1">
        <Button variant="primary" size="lg" loading={busy} onClick={() => signIn().catch(() => undefined)} className="self-start" data-testid="siwe">
          Sign message
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

function ProfileStep() {
  const refreshMe = useAuth((s) => s.refreshMe);
  const form = useForm<ParticipantFormInput, unknown, ParticipantForm>({
    resolver: zodResolver(participantSchema),
    defaultValues: { type: "prosumer", display_name: "", feeder_node_id: "n4", pv_capacity_kw: 3, battery_kwh: 0, ev_battery_kwh: undefined, ev_max_power_kw: undefined, ev_v2g: false },
    mode: "onBlur",
  });
  const type = form.watch("type");
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    if (type === "consumer") form.setValue("pv_capacity_kw", 0);
  }, [type, form]);

  const save = useMutation({
    mutationFn: async (v: ParticipantForm) => {
      const body = {
        type: v.type,
        display_name: v.display_name || null,
        feeder_node_id: v.feeder_node_id,
        pv_capacity_kw: v.type === "consumer" ? 0 : v.pv_capacity_kw,
        battery_kwh: v.battery_kwh,
        ev_battery_kwh: v.type === "ev" ? v.ev_battery_kwh ?? null : null,
        ev_max_power_kw: v.type === "ev" ? v.ev_max_power_kw ?? null : null,
        ev_v2g: v.type === "ev" ? v.ev_v2g : false,
      };
      return api.participants.create(body);
    },
    onSuccess: () => refreshMe(),
    onError: (e: Error) => setServerError(e.message),
  });

  return (
    <Card>
      <CardHeader title="Describe your home" description="This sets what you can buy and sell. It can be changed later." />
      <form onSubmit={form.handleSubmit((v) => { setServerError(null); save.mutate(v); })} noValidate>
        <CardBody className="grid gap-2 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Segmented
              name="type"
              label="Participant type"
              value={type}
              onChange={(v) => form.setValue("type", v, { shouldValidate: true })}
              options={[
                { value: "consumer", label: "Consumer", description: "Only uses energy" },
                { value: "prosumer", label: "Prosumer", description: "Generates or stores" },
                { value: "ev", label: "Electric vehicle", description: "Charges to a deadline" },
              ]}
            />
          </div>
          <Field id="display_name" label="Display name" unit="optional" error={form.formState.errors.display_name?.message}>
            <Input placeholder="e.g. House 12" {...form.register("display_name")} data-testid="display-name" />
          </Field>
          <Field id="feeder_node_id" label="Feeder node" error={form.formState.errors.feeder_node_id?.message} help="Where you connect on the local feeder">
            <Select {...form.register("feeder_node_id")}>
              {NODES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field id="pv" label="Solar capacity" unit="kW" error={form.formState.errors.pv_capacity_kw?.message} className={cn(type === "consumer" && "opacity-50")}>
            <Input type="number" step="0.1" min="0" inputMode="decimal" disabled={type === "consumer"} {...form.register("pv_capacity_kw")} />
          </Field>
          <Field id="battery" label="Home battery" unit="kWh" error={form.formState.errors.battery_kwh?.message}>
            <Input type="number" step="0.1" min="0" inputMode="decimal" {...form.register("battery_kwh")} />
          </Field>
          {type === "ev" && (
            <>
              <Field id="ev_battery" label="Vehicle battery" unit="kWh" error={form.formState.errors.ev_battery_kwh?.message}>
                <Input type="number" step="0.1" min="0" inputMode="decimal" {...form.register("ev_battery_kwh")} />
              </Field>
              <Field id="ev_power" label="Max charge power" unit="kW" error={form.formState.errors.ev_max_power_kw?.message}>
                <Input type="number" step="0.1" min="0" inputMode="decimal" {...form.register("ev_max_power_kw")} />
              </Field>
              <label className="flex items-center gap-1 text-sm sm:col-span-2">
                <input type="checkbox" {...form.register("ev_v2g")} className="h-2 w-2 accent-[var(--accent)]" />
                Vehicle-to-grid: allow selling from the vehicle battery
              </label>
            </>
          )}
          {serverError && (
            <p role="alert" className="text-xs text-danger sm:col-span-2">
              {serverError}
            </p>
          )}
        </CardBody>
        <CardFooter>
          <Button type="submit" variant="primary" loading={save.isPending} data-testid="save-profile">
            Save profile
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function FaucetStep({ onDone }: { onDone: () => void }) {
  const tx = useTx();
  const chain = useChainAccount();
  const claim = useMutation({
    mutationFn: () => tx.run({ ...contracts.MockINR, functionName: "faucet" }),
    onSuccess: onDone,
  });
  return (
    <Card>
      <CardHeader title="Get test INR" description={`The faucet mints ${formatInr(chainParams.faucetAmountPaise)} of test INR once per UTC day. It has no real value.`} />
      <CardBody className="flex flex-col gap-1">
        {chain.data?.claimedFaucetToday && (
          <p className="text-xs text-text-muted">This address already claimed today. Ask the operator for tokens or wait until tomorrow (UTC).</p>
        )}
        <TxStatusLine tx={tx} onRetry={() => claim.mutate()} />
      </CardBody>
      <CardFooter>
        <Button variant="primary" loading={claim.isPending} onClick={() => claim.mutate()} data-testid="faucet">
          Claim from faucet
        </Button>
      </CardFooter>
    </Card>
  );
}

function RegisterStep({ onDone }: { onDone: () => void }) {
  const { address } = useAccount();
  const tx = useTx();
  const chain = useChainAccount();
  const need = useMemo(() => {
    const have = chain.data?.stakePaise ?? 0n;
    return have >= chainParams.minStakePaise ? 0n : chainParams.minStakePaise - have;
  }, [chain.data]);
  const [stage, setStage] = useState<"idle" | "approve" | "stake" | "register">("idle");

  const run = useMutation({
    mutationFn: async () => {
      if (!address) throw new Error("Connect a wallet first.");
      if (need > 0n) {
        setStage("approve");
        await tx.run({ ...contracts.MockINR, functionName: "approve", args: [contracts.Registry.address, need] });
        setStage("stake");
        await tx.run({ ...contracts.Registry, functionName: "stake", args: [need] });
      }
      setStage("register");
      await tx.run({ ...contracts.Registry, functionName: "register", args: [demoMeterKeyHash(address)] });
    },
    onSuccess: onDone,
    onSettled: () => setStage("idle"),
  });

  return (
    <Card>
      <CardHeader
        title="Stake and register"
        description={`A stake of ${formatInr(chainParams.minStakePaise)} backs your promises. It can be slashed for non-delivery and withdrawn after a cooldown.`}
      />
      <CardBody className="flex flex-col gap-1 text-sm">
        <ol className="list-decimal pl-3 text-xs text-text-muted">
          <li className={cn(stage === "approve" && "text-text")}>Approve the Registry to take {formatInr(need)}{need === 0n && " (already staked)"}</li>
          <li className={cn(stage === "stake" && "text-text")}>Stake it</li>
          <li className={cn(stage === "register" && "text-text")}>Register your meter key</li>
        </ol>
        <TxStatusLine tx={tx} onRetry={() => run.mutate()} />
      </CardBody>
      <CardFooter>
        <Button variant="primary" loading={run.isPending} onClick={() => run.mutate()} data-testid="register">
          {need > 0n ? "Stake and register" : "Register"}
        </Button>
      </CardFooter>
    </Card>
  );
}
