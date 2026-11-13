import { Badge } from "@/components/ui/badge";
import type { IntervalState } from "@/lib/api/types";

export const STATE_META: Record<IntervalState, { label: string; tone: "neutral" | "accent" | "warning" | "success"; hint: string }> = {
  OPEN: { label: "Open", tone: "neutral", hint: "The interval has started. Commit window opens shortly." },
  COMMIT: { label: "Commit", tone: "accent", hint: "Submit a sealed position. Only its hash is visible." },
  REVEAL: { label: "Reveal", tone: "accent", hint: "Reveal your position so it can be priced and matched." },
  CLEARING: { label: "Clearing", tone: "warning", hint: "The engine is pricing and matching revealed positions." },
  SETTLED: { label: "Settled", tone: "success", hint: "Trades are posted and escrow has moved." },
  METERED: { label: "Metered", tone: "success", hint: "Deliveries verified against signed meter readings." },
};

export function IntervalBadge({ state }: { state: IntervalState }) {
  const m = STATE_META[state];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}
