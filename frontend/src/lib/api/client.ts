import type {
  AttackRunRequest,
  AttackRunResult,
  AuditLogOut,
  AuditReport,
  AuditRerunResponse,
  ConfigMap,
  FairnessBaseline,
  FairnessHistory,
  FlagOut,
  GridStatus,
  Health,
  Interval,
  MeResponse,
  NonceResponse,
  Orderbook,
  ParticipantCreate,
  ParticipantOut,
  ParticipantUpdate,
  Position,
  PositionCreate,
  PricePoint,
  Reputation,
  ReputationHistory,
  ReputationProof,
  SimControlState,
  TokenResponse,
  Trade,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? API_URL.replace(/^http/, "ws").replace(/\/$/, "") + "/ws";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

let tokenGetter: () => string | null = () => null;
/** Wired by the auth store so the client never imports React state. */
export function setTokenGetter(fn: () => string | null) {
  tokenGetter = fn;
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  const token = tokenGetter();
  if (init.auth !== false && token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the market server");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = readableDetail(body?.detail) ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function readableDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Pydantic validation errors
    return detail
      .map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.filter((l: unknown) => l !== "body").join(".") : "";
        return loc ? `${loc}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) s.set(k, String(v));
  const str = s.toString();
  return str ? `?${str}` : "";
};

export const api = {
  health: () => request<Health>("/health", { auth: false }),

  // Phase 6
  auth: {
    nonce: (address: string) =>
      request<NonceResponse>("/auth/nonce", {
        method: "POST",
        body: JSON.stringify({ address }),
        auth: false,
      }),
    verify: (address: string, message: string, signature: string) =>
      request<TokenResponse>("/auth/verify", {
        method: "POST",
        body: JSON.stringify({ address, message, signature }),
        auth: false,
      }),
  },
  me: () => request<MeResponse>("/me"),
  participants: {
    create: (body: ParticipantCreate) =>
      request<ParticipantOut>("/participants", { method: "POST", body: JSON.stringify(body) }),
    update: (id: number, body: ParticipantUpdate) =>
      request<ParticipantOut>(`/participants/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  },

  // Phase 7 (served by the mock until the teammate's backend lands)
  intervals: {
    current: () => request<Interval>("/intervals/current", { auth: false }),
    get: (id: number) => request<Interval>(`/intervals/${id}`, { auth: false }),
  },
  priceHistory: (limit = 96) =>
    request<PricePoint[]>(`/price-history${qs({ limit })}`, { auth: false }),
  orderbook: () => request<Orderbook>("/orderbook", { auth: false }),
  positions: {
    create: (body: PositionCreate) =>
      request<Position>("/positions", { method: "POST", body: JSON.stringify(body) }),
    reveal: (id: number, txHash: string) =>
      request<Position>(`/positions/${id}/reveal`, {
        method: "POST",
        body: JSON.stringify({ tx_hash: txHash }),
      }),
    mine: () => request<Position[]>("/positions/mine"),
  },
  trades: {
    list: (params: { limit?: number; mine?: boolean } = {}) =>
      request<Trade[]>(`/trades${qs(params)}`, { auth: !!params.mine }),
    get: (id: number) => request<Trade>(`/trades/${id}`, { auth: false }),
  },
  reputation: (address: string) =>
    request<Reputation>(`/reputation/${address}`, { auth: false }),
  reputationHistory: (address: string) =>
    request<ReputationHistory>(`/reputation/${address}/history`, { auth: false }),
  reputationProof: (address: string, intervalId: number) =>
    request<ReputationProof>(
      `/reputation/${address}/proof${qs({ interval_id: intervalId })}`,
      { auth: false },
    ),
  grid: () => request<GridStatus>("/grid/status", { auth: false }),
  fairnessHistory: (baseline: FairnessBaseline = "B3", limit = 96) =>
    request<FairnessHistory>(`/fairness/history${qs({ baseline, limit })}`, { auth: false }),

  // Phase 10
  audit: {
    get: (intervalId: number) =>
      request<AuditReport>(`/audit/${intervalId}`, { auth: false }),
    rerun: (intervalId: number) =>
      request<AuditRerunResponse>(`/audit/${intervalId}/rerun`, { method: "POST" }),
  },
  admin: {
    config: {
      get: () => request<ConfigMap>("/admin/config"),
      put: (values: Record<string, unknown>) =>
        request<ConfigMap>("/admin/config", {
          method: "PUT",
          body: JSON.stringify({ values }),
        }),
    },
    flags: {
      list: (status = "open") =>
        request<FlagOut[]>(`/admin/flags${qs({ status })}`),
      resolve: (id: number, body: { status: "resolved" | "dismissed"; note?: string }) =>
        request<FlagOut>(`/admin/flags/${id}/resolve`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
    },
    attacks: {
      run: (body: AttackRunRequest) =>
        request<AttackRunResult>("/admin/attacks/run", {
          method: "POST",
          body: JSON.stringify(body),
        }),
    },
    simulation: {
      get: () => request<SimControlState>("/admin/simulation"),
      start: () => request<SimControlState>("/admin/simulation/start", { method: "POST" }),
      stop: () => request<SimControlState>("/admin/simulation/stop", { method: "POST" }),
      speed: (interval_seconds: number) =>
        request<SimControlState>("/admin/simulation/speed", {
          method: "PUT",
          body: JSON.stringify({ interval_seconds }),
        }),
    },
    auditLog: (limit = 100) =>
      request<AuditLogOut[]>(`/admin/audit-log${qs({ limit })}`),
  },
};
