/**
 * API types.
 *
 * Auth and participant types come from the generated OpenAPI schema
 * (src/api/schema.d.ts). Market types match the FastAPI response contracts and the
 * frontend mock.
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
  demo_mode?: boolean;
  interval_seconds?: number;
  simulation_running?: boolean;
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

// ---- Phase 10 ---------------------------------------------------------------

export type AttackScenario =
  | "sybil_farm"
  | "collusion_ring"
  | "price_manipulation"
  | "false_reports"
  | "defect_after_trust";

export interface AttackRunRequest {
  scenario: AttackScenario;
  params: Record<string, number | string | boolean>;
  defenses: "on" | "off";
}

export interface AttackSeriesPoint {
  interval: number;
  p_ref?: number | null;
  sdr?: number | null;
  jain?: number | null;
  gini?: number | null;
  hhi?: number | null;
  mean_reputation?: number | null;
}

export interface AttackRunResult {
  id: number;
  scenario: AttackScenario;
  defenses: boolean;
  params: Record<string, unknown>;
  status: string;
  summary: Record<string, unknown>;
  series: AttackSeriesPoint[];
  attacker_profit_paise: number;
  plain_summary: string;
  created_at: string;
}

export interface HashTriple {
  stored: string | null;
  recomputed: string | null;
  on_chain: string | null;
  stored_matches_recomputed: boolean | null;
  stored_matches_on_chain: boolean | null;
  recomputed_matches_on_chain: boolean | null;
}

export interface AuditReport {
  interval_id: number;
  state: string;
  engine_version: string | null;
  p_ref_paise: number | null;
  sdr: number | null;
  positions: {
    participant_id: number;
    side: string;
    qty_wh: number;
    limit_price_paise: number;
    revealed: boolean;
  }[];
  trades: {
    buyer_id: number;
    seller_id: number;
    qty_wh: number;
    price_paise: number;
  }[];
  input_root: HashTriple;
  result_hash: HashTriple;
  merkle_leaves: Record<string, unknown>[];
  explorer: Record<string, string | null | undefined>;
}

export interface AuditRerunResponse {
  interval_id: number;
  engine_version_stored: string | null;
  engine_version_now: string;
  input_root: HashTriple;
  result_hash: HashTriple;
  match: boolean;
  note: string;
}

export interface FlagOut {
  id: number;
  participant_id: number | null;
  interval_id: number | null;
  kind: string;
  severity: string;
  status: string;
  detail: Record<string, unknown>;
  created_at: string;
  resolved_at: string | null;
  resolved_by: number | null;
}

export interface AuditLogOut {
  id: number;
  actor_user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export interface SimControlState {
  running: boolean;
  interval_seconds: number;
  override_active: boolean;
}

export interface ConfigMap {
  values: Record<string, number | string | boolean>;
}
