"use client";

import Link from "next/link";
import { TradesTable } from "@/components/trades-table";
import { Button } from "@/components/ui/button";
import { CardBody } from "@/components/ui/card";
import { Empty } from "@/components/ui/data-state";
import type { Trade } from "@/lib/api/types";

/** Recent cleared trades for the market page. */
export function TradesFeed({ trades }: { trades: Trade[] }) {
  if (!trades.length) {
    return (
      <Empty
        title="No trades yet this session"
        hint="Trades appear after an interval clears. Place a position on the Trade page to participate."
        action={
          <Button size="sm" asChild>
            <Link href="/trade">Go to Trade</Link>
          </Button>
        }
      />
    );
  }
  return (
    <CardBody className="px-0 py-0">
      <TradesTable trades={trades} />
    </CardBody>
  );
}
