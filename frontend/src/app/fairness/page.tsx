"use client";

import { useState } from "react";
import { FairnessCharts } from "@/components/fairness/fairness-charts";
import { MetricCards } from "@/components/fairness/metric-cards";
import { PageHeader } from "@/components/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Segmented } from "@/components/ui/field";
import { QueryState } from "@/components/ui/data-state";
import type { FairnessBaseline } from "@/lib/api/types";
import { useFairnessHistory } from "@/lib/queries";

export default function FairnessPage() {
  const [focus, setFocus] = useState<FairnessBaseline>("B3");
  const b3 = useFairnessHistory("B3", 96);
  const b2 = useFairnessHistory("B2", 96);
  const primary = focus === "B3" ? b3 : b2;
  const latest = primary.data?.metrics.length
    ? primary.data.metrics[primary.data.metrics.length - 1]
    : null;

  return (
    <>
      <PageHeader
        title="Fairness lab"
        description="Jain, Gini, HHI, small-actor parity, price impact and welfare efficiency over time, with a B2 versus B3 comparison."
        actions={
          <Segmented
            name="baseline"
            label="Metric cards baseline"
            value={focus}
            onChange={(v) => setFocus(v)}
            options={[
              { value: "B3", label: "B3 full system" },
              { value: "B2", label: "B2 SDR only" },
            ]}
          />
        }
      />

      <QueryState query={primary} rows={3}>
        {() => (
          <div className="mb-3">
            <MetricCards latest={latest} />
          </div>
        )}
      </QueryState>

      <Card>
        <CardHeader
          title="Baselines over time"
          description="B3 is the full system (reputation + grid). B2 is SDR pricing with proportional allocation and no reputation or feeder limits."
        />
        <CardBody>
          {b2.isPending || b3.isPending ? (
            <p className="text-sm text-text-muted">Loading fairness series…</p>
          ) : b2.isError || b3.isError ? (
            <p role="alert" className="text-sm text-danger">
              Could not load fairness history. Is the market API running?
            </p>
          ) : (
            <FairnessCharts b2={b2.data?.metrics ?? []} b3={b3.data?.metrics ?? []} />
          )}
        </CardBody>
      </Card>
    </>
  );
}
