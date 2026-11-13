import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { SdrGauge } from "./market/sdr-gauge";
import { TradesFeed } from "./market/trades-feed";
import { TierLadder } from "./reputation/tier-ladder";
import { ComponentRadar } from "./reputation/component-radar";
import { WhatIfPanel, intervalsToTrusted } from "./reputation/what-if-panel";
import { MetricCards } from "./fairness/metric-cards";
import { FeederMap, NodeParticipants } from "./grid/feeder-map";
import type { FairnessMetric, GridStatus, Reputation, Trade } from "@/lib/api/types";

function wrap(ui: ReactNode) {
  return render(<TooltipProvider>{ui}</TooltipProvider>);
}

describe("SdrGauge", () => {
  it("labels surplus and announces the ratio", () => {
    wrap(<SdrGauge sdr={2} />);
    expect(screen.getByText("Surplus")).toBeInTheDocument();
    expect(screen.getByText(/Supply to demand ratio 2\.00/i)).toBeInTheDocument();
  });
});

describe("TradesFeed", () => {
  it("shows empty guidance when there are no trades", () => {
    render(<TradesFeed trades={[]} />);
    expect(screen.getByText(/No trades yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Go to Trade/i })).toHaveAttribute("href", "/trade");
  });

  it("renders trade rows with units", () => {
    const trade: Trade = {
      id: 1,
      interval_id: 9,
      side: null,
      buyer: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      seller: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
      qty_wh: 1500,
      price_paise: 550,
      status: "cleared",
      created_at: new Date().toISOString(),
    };
    render(<TradesFeed trades={[trade]} />);
    expect(screen.getByText("Quantity (kWh)")).toBeInTheDocument();
    expect(screen.getByTestId("trade-row")).toBeInTheDocument();
  });
});

describe("TierLadder", () => {
  it("marks the current tier", () => {
    render(<TierLadder current="standard" />);
    expect(screen.getByText("You are here")).toBeInTheDocument();
    expect(screen.getByText("Trusted")).toBeInTheDocument();
  });
});

describe("ComponentRadar", () => {
  it("lists the four components as text", () => {
    render(
      <ComponentRadar components={{ delivery: 0.9, reveal: 1, honesty: 0.8, collusion: 0.1 }} />,
    );
    expect(screen.getByText("Delivery")).toBeInTheDocument();
    expect(screen.getByText("0.90")).toBeInTheDocument();
    expect(screen.getByText("Collusion-free")).toBeInTheDocument();
  });
});

describe("WhatIfPanel", () => {
  it("computes a finite path to Trusted for a newcomer", () => {
    expect(intervalsToTrusted(1, 2, 0, 1)).toBeGreaterThan(0);
    expect(intervalsToTrusted(1, 2, 0, 1)).toBeLessThanOrEqual(500);
  });

  it("exposes a delivery-rate control", async () => {
    const reputation: Reputation = {
      address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      score: 0.4,
      tier: "standard",
      components: { delivery: 0.7, reveal: 1, honesty: 0.9, collusion: 0.05 },
      evidence_count: 40,
      intervals_to_trusted: 60,
      volume_cap_kwh: 25,
      updated_at: new Date().toISOString(),
    };
    render(<WhatIfPanel reputation={reputation} />);
    const slider = screen.getByRole("slider");
    await userEvent.click(slider);
    expect(screen.getByText(/intervals to reach Trusted/i)).toBeInTheDocument();
  });
});

describe("MetricCards", () => {
  it("renders the six fairness metrics with tooltips", () => {
    const latest: FairnessMetric = {
      interval_id: 12,
      ends_at: new Date().toISOString(),
      baseline: "B3",
      jain: 0.91,
      gini: 0.18,
      hhi: 0.11,
      small_actor_parity: 0.97,
      price_impact: 0.02,
      welfare_efficiency: 0.94,
    };
    wrap(<MetricCards latest={latest} />);
    expect(screen.getByText("Jain index")).toBeInTheDocument();
    expect(screen.getByText("0.910")).toBeInTheDocument();
    expect(screen.getByText("Welfare efficiency")).toBeInTheDocument();
  });
});

describe("FeederMap", () => {
  const grid: GridStatus = {
    interval_id: 1,
    lines: [
      { id: "l_n0_n1", from_node: "n0", to_node: "n1", capacity_kw: 100, loading_pct: 40 },
      { id: "l_n1_n4", from_node: "n1", to_node: "n4", capacity_kw: 100, loading_pct: 82 },
    ],
    congested_line_ids: ["l_n1_n4"],
    max_loading_pct: 82,
    p2p_share_pct: 61,
    nodes: [
      { id: "n0", label: "Transformer", kind: "root", participants: [] },
      {
        id: "n4",
        label: "N4",
        kind: "feeder",
        participants: [{ address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8", kind: "prosumer" }],
      },
    ],
  };

  it("exposes nodes as buttons and lists participants", async () => {
    const onSelect = vi.fn();
    render(<FeederMap grid={grid} selectedId={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: /Node n4/i }));
    expect(onSelect).toHaveBeenCalledWith("n4");

    render(<NodeParticipants grid={grid} nodeId="n4" />);
    expect(screen.getByText(/prosumer/i)).toBeInTheDocument();
  });
});
