"use client";

import { useState } from "react";
import { AttackerProfitMeter } from "@/components/attack/attacker-profit-meter";
import { DefenseCharts } from "@/components/attack/defense-charts";
import { ParamSliders, type AttackParams } from "@/components/attack/param-sliders";
import { ScenarioPicker } from "@/components/attack/scenario-picker";
import { AttackSummary } from "@/components/attack/summary";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api/client";
import type { AttackRunResult, AttackScenario } from "@/lib/api/types";
import { useIsAdmin } from "@/lib/auth";

const DEFAULT_PARAMS: AttackParams = {
  participants: 40,
  days: 1,
  seed: 42,
  max_intervals: 24,
};

export default function AttackLabPage() {
  const isAdmin = useIsAdmin();
  const [scenario, setScenario] = useState<AttackScenario>("sybil_farm");
  const [params, setParams] = useState<AttackParams>(DEFAULT_PARAMS);
  const [off, setOff] = useState<AttackRunResult | null>(null);
  const [on, setOn] = useState<AttackRunResult | null>(null);
  const [busy, setBusy] = useState<"off" | "on" | "both" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (mode: "off" | "on" | "both") => {
    setError(null);
    setBusy(mode);
    try {
      if (mode === "off" || mode === "both") {
        const res = await api.admin.attacks.run({
          scenario,
          params: { ...params } as Record<string, number | string | boolean>,
          defenses: "off",
        });
        setOff(res);
      }
      if (mode === "on" || mode === "both") {
        const res = await api.admin.attacks.run({
          scenario,
          params: { ...params } as Record<string, number | string | boolean>,
          defenses: "on",
        });
        setOn(res);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.status === 403
            ? "Admin sign-in required to run attack scenarios."
            : err.detail
          : "Attack run failed.";
      setError(msg);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Attack lab"
        description="Run isolated Phase 4 attack scenarios with defenses off and on. Results never touch the live market."
      />

      {!isAdmin && (
        <p role="status" className="mb-3 rounded border border-warning bg-warning-soft px-2 py-1 text-sm text-text">
          Sign in with an admin wallet to run scenarios. Charts below stay empty until then.
        </p>
      )}

      <Card className="mb-3">
        <CardHeader title="Scenario" description="Pick an attack and set scale. Default runs are short for interactive use." />
        <CardBody className="space-y-3">
          <ScenarioPicker value={scenario} onChange={setScenario} />
          <ParamSliders value={params} onChange={setParams} />
          <div className="flex flex-wrap gap-1">
            <Button disabled={!isAdmin || busy !== null} onClick={() => run("both")}>
              {busy === "both" ? "Running…" : "Run off then on"}
            </Button>
            <Button variant="secondary" disabled={!isAdmin || busy !== null} onClick={() => run("off")}>
              Defenses off only
            </Button>
            <Button variant="secondary" disabled={!isAdmin || busy !== null} onClick={() => run("on")}>
              Defenses on only
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
        </CardBody>
      </Card>

      <div className="mb-3 grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader title="Attacker profit" description="Welfare gain of the attacker group versus grid-only trading." />
          <CardBody>
            <AttackerProfitMeter
              offPaise={off?.attacker_profit_paise ?? null}
              onPaise={on?.attacker_profit_paise ?? null}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="What happened" />
          <CardBody>
            <AttackSummary offText={off?.plain_summary} onText={on?.plain_summary} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Side-by-side" description="Price and fairness with defenses off versus on." />
        <CardBody>
          <DefenseCharts off={off} on={on} />
        </CardBody>
      </Card>
    </>
  );
}
