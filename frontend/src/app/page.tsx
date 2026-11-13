import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Ticker } from "@/components/ticker";
import { IntervalWalkthrough } from "@/components/interval-walkthrough";

export default function Landing() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 py-4 md:py-8">
      <div>
        <h1 className="text-3xl text-text">A fair, verifiable local energy market.</h1>
        <p className="mt-2 max-w-2xl text-base text-text-muted">
          Every fifteen minutes, neighbours with solar, batteries and electric vehicles trade energy
          directly with each other. One reference price is set from supply and demand and bounded by the
          feed-in and retail tariffs, so sellers earn more than the grid pays and buyers pay less than the
          grid charges. Sealed bids, on-chain escrow and a reputation score built from real deliveries keep
          the market honest; the grid stays in place for physical delivery and anything left unmatched.
        </p>
        <div className="mt-3 flex flex-wrap gap-1">
          <Button variant="primary" size="lg" asChild>
            <Link href="/onboarding">
              Start onboarding <ArrowRight className="h-2 w-2" aria-hidden />
            </Link>
          </Button>
          <Button size="lg" asChild>
            <Link href="/dashboard">Open the dashboard</Link>
          </Button>
        </div>
      </div>

      <section aria-labelledby="live-heading">
        <h2 id="live-heading" className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
          Live market
        </h2>
        <Ticker />
      </section>

      <section aria-labelledby="walk-heading">
        <h2 id="walk-heading" className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
          One interval, step by step
        </h2>
        <IntervalWalkthrough />
      </section>

      <p className="text-xs text-text-faint">
        Simulated meters and a simulated feeder. Local test network; nothing here has monetary value.
      </p>
    </div>
  );
}
