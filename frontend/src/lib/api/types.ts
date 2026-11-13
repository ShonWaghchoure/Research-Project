/**
 * API types.
 *
 * Phase 6 types come from the generated OpenAPI schema (src/api/schema.d.ts).
 * Phase 7 (market lifecycle) is being built by a teammate; the types below follow the
 * Phase 7 section of GEMINI.md and are served by mock/server.mjs until the real backend
 * lands. When it does, regenerate the schema (`make gen-api`) and reconcile this file.
 */
import type { components } from "@/api/schema";

export type NonceResponse = components["schemas"]["NonceResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type MeResponse = components["schemas"]["MeResponse"];
export type ParticipantOut = components["schemas"]["ParticipantOut"];
export type ParticipantCreate = components["schemas"]["ParticipantCreate"];
export type ParticipantUpdate = components["schemas"]["ParticipantUpdate"];

export interface Health {
  status: string;
  postgres: string;
  redis: string;
  chain_rpc: string;
  block_number: number | null;
  chain_id: number;
}

// ---- Phase 7 (assumed shapes) -------------------------------------------------

export type IntervalState = "OPEN" | "COMMIT" | "REVEAL" | "CLEARING" | "SETTLED" | "METERED";

export interface Interval {
  id: number;
  state: IntervalState;
  starts_at: string;
  ends_at: string;
  commit_deadline: string;
  reveal_deadline: string;
  p_ref_paise: number | null;
  prev_p_ref_paise: number | null;
  sdr: number | null;
  active_participants: number;
  input_root: string | null;
  result_hash: string | null;
}

export interface PricePoint {
  interval_id: number;
  ends_at: string;
  p_ref_paise: number;
  sdr: number;
}

export type Side = "buy" | "sell";

export interface PositionCreate {
  interval_id: number;
  side: Side;
  qty_wh: number;
  limit_price_paise: number;
  /** Unix seconds, 0 for none. */
  deadline: number;
  salt: `0x${string}`;
}

export interface Position {
  id: number;
  interval_id: number;
  side: Side;
  qty_wh: number;
  limit_price_paise: number;
  deadline: number;
  salt: `0x${string}`;
  commit_hash: `0x${string}`;
  committed_tx: string | null;
  revealed: boolean;
  created_at: string;
}

export interface Orderbook {
  interval_id: number;
  supply_wh: number;
  demand_wh: number;
  bids: { price_paise: number; qty_wh: number }[];
  asks: { price_paise: number; qty_wh: number }[];
}

export type TradeStatus = "cleared" | "settled" | "delivered" | "shortfall";

export interface Trade {
  id: number;
  interval_id: number;
  /** Set when the caller is a party to the trade. */
  side: Side | null;
  buyer: string;
  seller: string;
  qty_wh: number;
  price_paise: number;
  status: TradeStatus;
  created_at: string;
}

export type Tier = "suspended" | "probation" | "standard" | "trusted";

export interface Reputation {
  address: string;
  score: number;
  tier: Tier;
  components: { delivery: number; reveal: number; honesty: number; collusion: number };
  evidence_count: number;
  intervals_to_trusted: number | null;
  volume_cap_kwh: number;
  updated_at: string;
}

export interface GridLine {
  id: string;
  from_node: string;
  to_node: string;
  capacity_kw: number;
  loading_pct: number;
}

export interface GridParticipant {
  address: string;
  kind: string;
}

export interface GridNode {
  id: string;
  label: string;
  kind: "root" | "feeder" | string;
  participants: GridParticipant[];
}

export interface GridStatus {
  interval_id: number;
  lines: GridLine[];
  congested_line_ids: string[];
  max_loading_pct: number;
  p2p_share_pct: number;
  /** Present from Phase 9 mock / backend. */
  nodes?: GridNode[];
}

export interface ReputationHistoryPoint {
  interval_id: number;
  ends_at: string;
  score: number;
  score_bp: number;
  tier: Tier;
  evidence_count: number;
  components: Reputation["components"];
}

export interface ReputationHistory {
  address: string;
  history: ReputationHistoryPoint[];
}

export interface ReputationProof {
  address: string;
  interval_id: number;
  score_bp: number;
  evidence_count: number;
  leaf_hash: string;
  proof: `0x${string}`[];
  root: `0x${string}`;
}

export type FairnessBaseline = "B2" | "B3";

export interface FairnessMetric {
  interval_id: number;
  ends_at: string;
  baseline: FairnessBaseline;
  jain: number;
  gini: number;
  hhi: number;
  small_actor_parity: number;
  price_impact: number;
  welfare_efficiency: number;
}

export interface FairnessHistory {
  baseline: FairnessBaseline;
  metrics: FairnessMetric[];
}

export interface WsMessage<T = unknown> {
  channel: "interval" | "price" | "trades" | "reputation" | "flags" | "grid";
  type: string;
  data: T;
}
