"use client";

import { PageHeader } from "@/components/page-header";
import { DepthChart } from "@/components/market/depth-chart";
import { PriceBandChart } from "@/components/market/price-band-chart";
import { SdrGauge } from "@/components/market/sdr-gauge";
import { TradesFeed } from "@/components/market/trades-feed";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { QueryState } from "@/components/ui/data-state";
import { InfoTip } from "@/components/ui/tooltip";
import { useTweenedNumber } from "@/components/ticker";
import { formatKwh, formatSdr, paiseToInr } from "@/lib/format";
import { useCurrentInterval, useOrderbook, usePriceHistory, useTrades } from "@/lib/queries";

export default function MarketPage() {
  const interval = useCurrentInterval();
  const history = usePriceHistory(96);
  const orderbook = useOrderbook();
  const trades = useTrades(false, 30);
  const iv = interval.data;
  const price = useTweenedNumber(iv?.p_ref_paise ?? iv?.prev_p_ref_paise ?? null);

  return (
    <>
      <PageHeader
        title="Market"
        description="Live clearing price, supply-to-demand balance, anonymised depth and recent trades."
      />

      <div className="mb-3 grid grid-cols-2 gap-1 md:grid-cols-4">
        <Stat
          label="Reference price"
          value={price === null ? "—" : paiseToInr(Math.round(price))}
          unit="₹/kWh"
          live
          hint={
            <span className="inline-flex items-center gap-0.5">
              Against feed-in ₹3.00 and retail ₹8.00
              <InfoTip label="How the price is formed">
                <ol className="list-decimal space-y-0.5 pl-3">
                  <li>Reputation-weight each position and cap quantities at 3× the side median.</li>
                  <li>SDR = weighted supply ÷ weighted demand.</li>
                  <li>Raw price = p_fit + (p_ret − p_fit) / (1 + SDR²).</li>
                  <li>Smooth 70% toward the new raw price, 30% toward the previous interval, then clip to the band.</li>
                </ol>
              </InfoTip>
            </span>
          }
        />
        <Stat label="Supply ÷ demand" value={formatSdr(iv?.sdr)} unit="SDR" />
        <Stat
          label="Book demand"
          value={orderbook.data ? formatKwh(orderbook.data.demand_wh, false) : "—"}
          unit="kWh"
        />
        <Stat
          label="Book supply"
          value={orderbook.data ? formatKwh(orderbook.data.supply_wh, false) : "—"}
          unit="kWh"
        />
      </div>

      <div className="grid gap-2 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Price against the tariff band"
            description="Each point is one cleared interval"
            action={
              <InfoTip label="Price formation">
                All matched trades clear at the same reference price. Unmatched demand buys from the grid at retail;
                unmatched supply exports at the feed-in tariff.
              </InfoTip>
            }
          />
          <QueryState
            query={history}
            rows={4}
            empty={{ when: (d) => d.length === 0, title: "No price history yet", hint: "Points appear after the first clearing." }}
          >
            {(data) => (
              <CardBody>
                <PriceBandChart data={data} />
              </CardBody>
            )}
          </QueryState>
        </Card>

        <Card>
          <CardHeader title="SDR gauge" description="Balance of the current book" />
          <CardBody className="flex justify-center">
            <SdrGauge
              sdr={
                iv?.sdr ??
                (orderbook.data && orderbook.data.demand_wh > 0
                  ? orderbook.data.supply_wh / orderbook.data.demand_wh
                  : null)
              }
            />
          </CardBody>
        </Card>
      </div>

      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        <Card>
          <CardHeader title="Depth" description="Anonymised cumulative bids and asks" />
          <QueryState
            query={orderbook}
            rows={4}
            empty={{
              when: (d) => d.bids.length === 0 && d.asks.length === 0,
              title: "Order book is empty",
              hint: "Depth fills during the commit window.",
            }}
          >
            {(book) => (
              <CardBody>
                <DepthChart book={book} />
              </CardBody>
            )}
          </QueryState>
        </Card>

        <Card>
          <CardHeader title="Trades feed" description="Most recent cleared matches" />
          <QueryState query={trades} rows={4}>
            {(rows) => <TradesFeed trades={rows} />}
          </QueryState>
        </Card>
      </div>
    </>
  );
}
