import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { Stepper } from "./ui/stepper";
import { Empty, ErrorState, QueryState } from "./ui/data-state";
import { TxStatusLine } from "./tx-status";
import { TradesTable } from "./trades-table";
import { ReputationGauge, TierBadge } from "./reputation-gauge";
import { CountdownRing } from "./countdown-ring";
import { Segmented } from "./ui/field";
import type { Reputation, Trade } from "@/lib/api/types";

describe("Stepper", () => {
  it("shows status as text, not colour alone", () => {
    render(
      <Stepper
        steps={[
          { id: "a", title: "Seal", status: "done" },
          { id: "b", title: "Commit", status: "active" },
          { id: "c", title: "Reveal", status: "todo" },
        ]}
      />,
    );
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    expect(screen.getByText("not started")).toBeInTheDocument();
    expect(screen.getByText("2. Commit").closest("li")).toHaveAttribute("aria-current", "step");
  });
});

describe("data states", () => {
  it("error state retries", async () => {
    const retry = vi.fn();
    render(<ErrorState message="boom" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry).toHaveBeenCalled();
  });

  it("QueryState picks loading, empty and data", () => {
    const base = { isError: false, error: null, refetch: () => undefined };
    const { rerender } = render(
      <QueryState query={{ ...base, data: undefined, isPending: true }}>{() => <p>data</p>}</QueryState>,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
    rerender(
      <QueryState query={{ ...base, data: [] as number[], isPending: false }} empty={{ when: (d) => d.length === 0, title: "Nothing" }}>
        {() => <p>data</p>}
      </QueryState>,
    );
    expect(screen.getByText("Nothing")).toBeInTheDocument();
    rerender(<QueryState query={{ ...base, data: [1], isPending: false }}>{() => <p>data</p>}</QueryState>);
    expect(screen.getByText("data")).toBeInTheDocument();
  });

  it("empty state renders hint", () => {
    render(<Empty title="No trades" hint="Place one" />);
    expect(screen.getByText("Place one")).toBeInTheDocument();
  });
});

describe("TxStatusLine", () => {
  it("renders nothing when idle and the readable reason on failure", () => {
    const { container, rerender } = render(<TxStatusLine tx={{ status: "idle", hash: null, error: null }} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<TxStatusLine tx={{ status: "failed", hash: "0xabc", error: "Commit window closed." }} />);
    expect(screen.getByText("Transaction failed")).toBeInTheDocument();
    expect(screen.getByText("Commit window closed.")).toBeInTheDocument();
  });
});

describe("TradesTable", () => {
  const trade: Trade = {
    id: 1, interval_id: 9, side: "buy", buyer: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    seller: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", qty_wh: 1500, price_paise: 550, status: "delivered",
    created_at: new Date().toISOString(),
  };
  it("labels units in headers and shows values", () => {
    render(<TradesTable trades={[trade]} mine />);
    expect(screen.getByText("Quantity (kWh)")).toBeInTheDocument();
    expect(screen.getByText("Price (₹/kWh)")).toBeInTheDocument();
    expect(screen.getByText("1.5")).toBeInTheDocument();
    expect(screen.getByText("5.50")).toBeInTheDocument();
    expect(screen.getByText("8.25")).toBeInTheDocument();
    expect(screen.getByText("Delivered")).toBeInTheDocument();
  });
});

describe("Reputation", () => {
  const rep: Reputation = {
    address: "0x1", score: 0.42, tier: "standard",
    components: { delivery: 0.5, reveal: 1, honesty: 1, collusion: 0 },
    evidence_count: 30, intervals_to_trusted: 70, volume_cap_kwh: 25, updated_at: "",
  };
  it("shows score, tier text and path to Trusted", () => {
    render(
      <TooltipProvider>
        <ReputationGauge reputation={rep} />
      </TooltipProvider>,
    );
    expect(screen.getAllByText("0.42").length).toBeGreaterThan(0);
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("70")).toBeInTheDocument();
  });
  it("tier badge has text", () => {
    render(<TierBadge tier="trusted" />);
    expect(screen.getByText("Trusted")).toBeInTheDocument();
  });
});

describe("CountdownRing", () => {
  it("shows remaining time with a label", () => {
    const now = Date.now();
    render(<CountdownRing startsAt={new Date(now - 30_000).toISOString()} endsAt={new Date(now + 90_000).toISOString()} label="to commit" />);
    expect(screen.getByText("to commit")).toBeInTheDocument();
    // Shown visually (aria-hidden) and once more as screen-reader text.
    expect(screen.getAllByText(/1:(29|30)/).length).toBe(2);
    expect(screen.getByText(/remaining/)).toHaveClass("sr-only");
  });
});

describe("Segmented", () => {
  it("is a keyboard-operable radio group", async () => {
    const onChange = vi.fn();
    render(
      <Segmented name="side" label="Side" value="buy" onChange={onChange} options={[{ value: "buy", label: "Buy" }, { value: "sell", label: "Sell" }]} />,
    );
    const sell = screen.getByRole("radio", { name: /sell/i });
    await userEvent.click(sell);
    expect(onChange).toHaveBeenCalledWith("sell");
  });
});
