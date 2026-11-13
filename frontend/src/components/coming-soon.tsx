import Link from "next/link";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Empty } from "@/components/ui/data-state";
import { Button } from "@/components/ui/button";

/** Calm placeholder for pages that arrive with Phase 9. */
export function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} description={description} />
      <Card>
        <Empty
          title="Available in the next release"
          hint="This view is part of the market-views phase. The dashboard and trade pages are complete."
          action={
            <Button size="sm" asChild>
              <Link href="/dashboard">Back to dashboard</Link>
            </Button>
          }
        />
      </Card>
    </>
  );
}
