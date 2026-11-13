/**
 * Mock Phase 7 backend.
 *
 * Serves the Phase 6 auth/participant endpoints and the Phase 7 market endpoints
 * described in GEMINI.md, with a real interval state machine, bots, SDR pricing
 * (same formula as backend/app/engine/pricing.py) and a WebSocket feed.
 *
 * It also acts as the market operator on the local Hardhat chain: it opens each
 * interval in Settlement so commitPosition works, and it verifies reveals against
 * the on-chain commit. Without a reachable chain it runs chain-less.
 *
 * Usage: node mock/server.mjs   (PORT=8001 MOCK_INTERVAL_SECONDS=60 RPC_URL=http://127.0.0.1:8545)
 *
 * Replace with the teammate's Phase 7 backend by pointing NEXT_PUBLIC_API_URL at it.
 */
import http from "node:http";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { WebSocketServer } from "ws";
import { createPublicClient, createWalletClient, encodeAbiParameters, getAddress, http as viemHttp, keccak256, verifyMessage } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { hardhat } from "viem/chains";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT ?? 8001);
const INTERVAL_SECONDS = Number(process.env.MOCK_INTERVAL_SECONDS ?? 60);
const RPC_URL = process.env.RPC_URL ?? "http://127.0.0.1:8545";
const OPERATOR_PK = process.env.OPERATOR_PRIVATE_KEY ?? "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";

const deployments = JSON.parse(readFileSync(path.join(__dirname, "..", "src", "contracts", "localhost.json"), "utf8"));
const SETTLEMENT = deployments.contracts.Settlement;

const P_FIT = 300, P_RET = 800, K = 2, ALPHA = 0.7;

// ---- chain --------------------------------------------------------------------
const publicClient = createPublicClient({ chain: hardhat, transport: viemHttp(RPC_URL) });
const operator = privateKeyToAccount(OPERATOR_PK);
const walletClient = createWalletClient({ account: operator, chain: hardhat, transport: viemHttp(RPC_URL) });
let chainOk = false;

async function probeChain() {
  try {
    await publicClient.getBlockNumber();
    chainOk = true;
  } catch {
    chainOk = false;
  }
  return chainOk;
}

async function openOnChain(iv) {
  if (!(await probeChain())) return;
  try {
    const hash = await walletClient.writeContract({
      address: SETTLEMENT.address,
      abi: SETTLEMENT.abi,
      functionName: "openInterval",
      args: [BigInt(iv.id), BigInt(Math.floor(new Date(iv.commit_deadline).getTime() / 1000)), BigInt(Math.floor(new Date(iv.reveal_deadline).getTime() / 1000))],
    });
    await publicClient.waitForTransactionReceipt({ hash });
    iv.on_chain = true;
  } catch (e) {
    console.warn(`[mock] openInterval(${iv.id}) failed: ${String(e.shortMessage ?? e.message).split("\n")[0]}`);
  }
}

async function onChainCommit(intervalId, address) {
  if (!chainOk) return null;
  try {
    return await publicClient.readContract({ address: SETTLEMENT.address, abi: SETTLEMENT.abi, functionName: "commits", args: [BigInt(intervalId), address] });
  } catch {
    return null;
  }
}

// ---- state --------------------------------------------------------------------
const users = new Map(); // address -> { id, address, role, nonce, nonceUsed, participant }
const tokens = new Map(); // token -> address
const positions = []; // user positions
const trades = [];
const priceHistory = [];
const reputations = new Map(); // address -> { alpha, beta, evidence }
let intervals = [];
let current = null;
let nextIntervalId = Number(process.env.MOCK_FIRST_INTERVAL ?? Math.floor(Date.now() / 1000) % 100000);
let nextId = 1;
let prevPRef = null;

const NODES = ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "n10", "n11", "n12"];
const LINES = [["n0", "n1"], ["n0", "n2"], ["n0", "n3"], ["n1", "n4"], ["n1", "n5"], ["n1", "n6"], ["n2", "n7"], ["n3", "n8"], ["n3", "n9"], ["n7", "n10"], ["n10", "n11"], ["n10", "n12"]];

function pseudo(i) {
  return getAddress(`0x${keccak256(encodeAbiParameters([{ type: "uint256" }], [BigInt(1000 + i)])).slice(26)}`);
}
const BOTS = Array.from({ length: 24 }, (_, i) => ({ address: pseudo(i), node: NODES[i % NODES.length], seller: i % 3 !== 0 }));

let botBook = { bids: [], asks: [], supply_wh: 0, demand_wh: 0 };
function makeBotBook(seed) {
  const r = mulberry32(seed);
  const hour = new Date().getHours();
  const sunny = hour >= 9 && hour <= 16;
  const bids = [], asks = [];
  let supply = 0, demand = 0;
  for (const b of BOTS) {
    const qty = Math.round((500 + r() * 2500) * (b.seller ? (sunny ? 1.4 : 0.6) : 1));
    const price = Math.round(b.seller ? 320 + r() * 250 : 520 + r() * 260);
    if (b.seller) { asks.push({ price_paise: price, qty_wh: qty }); supply += qty; }
    else { bids.push({ price_paise: price, qty_wh: qty }); demand += qty; }
  }
  bids.sort((a, b) => b.price_paise - a.price_paise);
  asks.sort((a, b) => a.price_paise - b.price_paise);
  return { bids, asks, supply_wh: supply, demand_wh: demand };
}
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function priceFromSdr(s) {
  if (!Number.isFinite(s)) return P_FIT;
  return Math.min(P_RET, Math.max(P_FIT, P_FIT + (P_RET - P_FIT) / (1 + Math.pow(s, K))));
}
function referencePrice(s) {
  const raw = priceFromSdr(s);
  return Math.round(prevPRef === null ? raw : ALPHA * raw + (1 - ALPHA) * prevPRef);
}

function rep(address) {
  const a = address.toLowerCase();
  if (!reputations.has(a)) reputations.set(a, { alpha: 1, beta: 2, evidence: 0, reveal: 1, honesty: 1, collusion: 0 });
  return reputations.get(a);
}
function repOut(address) {
  const r = rep(address);
  const n = r.alpha + r.beta;
  const mu = r.alpha / n;
  const sd = Math.sqrt((r.alpha * r.beta) / (n * n * (n + 1)));
  const score = Math.max(0, Math.min(1, mu - sd));
  const tier = r.evidence < 20 || score < 0.3 ? "probation" : score >= 0.8 && r.evidence >= 100 ? "trusted" : "standard";
  const toTrusted = tier === "trusted" ? null : Math.max(100 - r.evidence, Math.ceil((0.8 * 3 - 1) / (1 - 0.8)) - r.alpha + 1, 0);
  return {
    address,
    score: Number(score.toFixed(4)),
    tier,
    components: { delivery: Number(mu.toFixed(3)), reveal: r.reveal, honesty: r.honesty, collusion: r.collusion },
    evidence_count: r.evidence,
    intervals_to_trusted: toTrusted,
    volume_cap_kwh: tier === "probation" ? 5 : tier === "standard" ? 25 : 100,
    updated_at: new Date().toISOString(),
  };
}

// ---- interval state machine ------------------------------------------------------
const PHASES = [["OPEN", 0.0], ["COMMIT", 0.08], ["REVEAL", 0.5], ["CLEARING", 0.75], ["SETTLED", 0.83], ["METERED", 0.92]];

function newInterval() {
  const start = Date.now();
  const ms = INTERVAL_SECONDS * 1000;
  const iv = {
    id: nextIntervalId++,
    state: "OPEN",
    starts_at: new Date(start).toISOString(),
    ends_at: new Date(start + ms).toISOString(),
    commit_deadline: new Date(start + ms * 0.5).toISOString(),
    reveal_deadline: new Date(start + ms * 0.75).toISOString(),
    p_ref_paise: null,
    prev_p_ref_paise: prevPRef,
    sdr: null,
    active_participants: BOTS.length + users.size,
    input_root: null,
    result_hash: null,
    on_chain: false,
  };
  intervals.push(iv);
  if (intervals.length > 200) intervals.shift();
  botBook = makeBotBook(iv.id);
  current = iv;
  openOnChain(iv);
  broadcast("interval", "opened", publicInterval(iv));
  return iv;
}

function publicInterval(iv) {
  const { on_chain, ...rest } = iv;
  return rest;
}

function tick() {
  if (!current) newInterval();
  const iv = current;
  const t = (Date.now() - new Date(iv.starts_at).getTime()) / (INTERVAL_SECONDS * 1000);
  if (t >= 1) {
    // Unrevealed commits become reveal misses.
    for (const p of positions) if (p.interval_id === iv.id && !p.revealed) rep(p.address).reveal = Math.max(0, rep(p.address).reveal - 0.1);
    newInterval();
    return;
  }
  let state = "OPEN";
  for (const [name, from] of PHASES) if (t >= from) state = name;
  // Never advertise COMMIT before the interval is open on chain, or wallets will
  // commit into an interval the contract does not know yet.
  if (state === "COMMIT" && chainOk && !iv.on_chain) state = "OPEN";
  if (state !== iv.state) {
    iv.state = state;
    if (state === "CLEARING") clear(iv);
    if (state === "SETTLED") for (const tr of trades) if (tr.interval_id === iv.id) tr.status = "settled";
    if (state === "METERED") meter(iv);
    broadcast("interval", "state", publicInterval(iv));
  }
}

function clear(iv) {
  const revealed = positions.filter((p) => p.interval_id === iv.id && p.revealed);
  let supply = botBook.supply_wh, demand = botBook.demand_wh;
  for (const p of revealed) (p.side === "sell" ? (supply += p.qty_wh) : (demand += p.qty_wh));
  const s = demand > 0 ? supply / demand : supply > 0 ? Infinity : 1;
  const pRef = referencePrice(s);
  iv.sdr = Number(s.toFixed(4));
  iv.p_ref_paise = pRef;
  iv.input_root = keccak256(encodeAbiParameters([{ type: "uint256" }, { type: "uint256" }], [BigInt(iv.id), BigInt(revealed.length)]));
  iv.result_hash = keccak256(encodeAbiParameters([{ type: "uint256" }, { type: "uint32" }], [BigInt(iv.id), pRef]));
  prevPRef = pRef;
  priceHistory.push({ interval_id: iv.id, ends_at: iv.ends_at, p_ref_paise: pRef, sdr: iv.sdr });
  if (priceHistory.length > 500) priceHistory.shift();
  broadcast("price", "cleared", { interval_id: iv.id, p_ref_paise: pRef, sdr: iv.sdr });

  const r = mulberry32(iv.id * 7);
  // User trades first (reputation ordering is simulated by priority here).
  for (const p of revealed) {
    const ok = p.side === "buy" ? p.limit_price_paise >= pRef : p.limit_price_paise <= pRef;
    if (!ok) continue;
    const cp = BOTS[Math.floor(r() * BOTS.length)].address;
    pushTrade({ interval_id: iv.id, buyer: p.side === "buy" ? p.address : cp, seller: p.side === "sell" ? p.address : cp, qty_wh: p.qty_wh, price_paise: pRef });
  }
  // Bot-bot trades.
  const n = 5 + Math.floor(r() * 5);
  for (let i = 0; i < n; i++) {
    const buyer = BOTS.filter((b) => !b.seller)[Math.floor(r() * 8)];
    const seller = BOTS.filter((b) => b.seller)[Math.floor(r() * 16)];
    pushTrade({ interval_id: iv.id, buyer: buyer.address, seller: seller.address, qty_wh: Math.round(300 + r() * 1500), price_paise: pRef });
  }
  broadcast("grid", "updated", gridStatus());
}

function pushTrade(t) {
  const trade = { id: nextId++, status: "cleared", created_at: new Date().toISOString(), ...t };
  trades.unshift(trade);
  if (trades.length > 1000) trades.pop();
  broadcast("trades", "new", { ...trade, side: null });
}

function meter(iv) {
  for (const tr of trades) {
    if (tr.interval_id !== iv.id) continue;
    tr.status = "delivered";
    for (const a of [tr.buyer, tr.seller]) {
      if (!users.has(a)) continue;
      const r = rep(a);
      r.alpha += 1;
      r.evidence += 1;
      broadcast("reputation", "updated", repOut(a));
    }
  }
}

function gridStatus() {
  const r = mulberry32((current?.id ?? 1) * 13);
  const lines = LINES.map(([a, b]) => ({ id: `l_${a}_${b}`, from_node: a, to_node: b, capacity_kw: 100, loading_pct: Number((15 + r() * 60).toFixed(1)) }));
  const congested = lines.filter((l) => l.loading_pct > 70).map((l) => l.id);
  return {
    interval_id: current?.id ?? 0,
    lines,
    congested_line_ids: congested,
    max_loading_pct: Math.max(...lines.map((l) => l.loading_pct)),
    p2p_share_pct: Number((55 + r() * 20).toFixed(1)),
  };
}

// ---- helpers --------------------------------------------------------------------
function commitHash(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt) {
  return keccak256(
    encodeAbiParameters(
      [{ type: "uint256" }, { type: "address" }, { type: "uint8" }, { type: "uint64" }, { type: "uint32" }, { type: "uint64" }, { type: "bytes32" }],
      [BigInt(intervalId), participant, side === "buy" ? 0 : 1, BigInt(qtyWh), limitPricePaise, BigInt(deadline), salt],
    ),
  );
}

function siweMessage(address, nonce) {
  const issued = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
  return `localhost wants you to sign in with your Ethereum account:\n${address}\n\nSign in to Fair and Trustworthy P2P Energy Trading.\n\nURI: http://localhost:3000\nVersion: 1\nChain ID: 31337\nNonce: ${nonce}\nIssued At: ${issued}`;
}

function participantOut(u) {
  const p = u.participant;
  return { id: p.id, address: u.address, role: u.role, ...p };
}

// ---- http -------------------------------------------------------------------------
class HttpError extends Error {
  constructor(status, detail) { super(detail); this.status = status; }
}

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,OPTIONS" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

function auth(req) {
  const h = req.headers.authorization ?? "";
  const tok = h.startsWith("Bearer ") ? h.slice(7) : null;
  const address = tok && tokens.get(tok);
  if (!address) throw new HttpError(401, "not authenticated");
  return users.get(address);
}

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (raw.length > 64 * 1024) throw new HttpError(413, "request too large");
  return raw ? JSON.parse(raw) : {};
}

async function route(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const p = url.pathname;
  const m = req.method;

  if (m === "OPTIONS") return json(res, 204);
  if (p === "/health") return json(res, 200, { status: "ok", postgres: "mock", redis: "mock", chain_rpc: chainOk ? "ok" : "down", block_number: chainOk ? Number(await publicClient.getBlockNumber()) : null, chain_id: 31337 });
  if (p === "/docs") { res.writeHead(200, { "Content-Type": "text/plain" }); return res.end("Mock Phase 7 API. See frontend/mock/server.mjs."); }

  // auth
  if (p === "/auth/nonce" && m === "POST") {
    const { address } = await readBody(req);
    let addr;
    try { addr = getAddress(address); } catch { throw new HttpError(422, "invalid address"); }
    if (!users.has(addr)) users.set(addr, { id: users.size + 1, address: addr, role: "participant", participant: null });
    const u = users.get(addr);
    u.nonce = randomBytes(16).toString("hex");
    u.nonceUsed = false;
    return json(res, 200, { address: addr, nonce: u.nonce, message: siweMessage(addr, u.nonce), chain_id: 31337 });
  }
  if (p === "/auth/verify" && m === "POST") {
    const { address, message, signature } = await readBody(req);
    const addr = getAddress(address);
    const u = users.get(addr);
    if (!u || !u.nonce || u.nonceUsed) throw new HttpError(401, "nonce required");
    if (!message.includes(`Nonce: ${u.nonce}`)) throw new HttpError(401, "nonce mismatch");
    const ok = await verifyMessage({ address: addr, message, signature });
    if (!ok) throw new HttpError(401, "signature does not match address");
    u.nonceUsed = true;
    const tok = `mock.${randomBytes(24).toString("hex")}`;
    tokens.set(tok, addr);
    return json(res, 200, { access_token: tok, token_type: "bearer", role: u.role, address: addr });
  }
  if (p === "/me" && m === "GET") {
    const u = auth(req);
    return json(res, 200, { user_id: u.id, address: u.address, role: u.role, participant: u.participant ? participantOut(u) : null });
  }
  if (p === "/participants" && m === "POST") {
    const u = auth(req);
    if (u.participant) throw new HttpError(409, "participant already exists");
    const b = await readBody(req);
    if (!["consumer", "prosumer", "ev"].includes(b.type)) throw new HttpError(422, "type: invalid");
    if (b.type === "ev" && (b.ev_battery_kwh == null || b.ev_max_power_kw == null)) throw new HttpError(422, "ev_battery_kwh and ev_max_power_kw are required for type=ev");
    if (b.type === "consumer" && b.pv_capacity_kw > 0) throw new HttpError(422, "consumer cannot have pv_capacity_kw > 0");
    if (!NODES.includes(b.feeder_node_id)) throw new HttpError(422, "feeder_node_id: unknown node");
    u.participant = { id: u.id, type: b.type, display_name: b.display_name ?? null, feeder_node_id: b.feeder_node_id, pv_capacity_kw: b.pv_capacity_kw ?? 0, battery_kwh: b.battery_kwh ?? 0, ev_battery_kwh: b.ev_battery_kwh ?? null, ev_max_power_kw: b.ev_max_power_kw ?? null, ev_v2g: !!b.ev_v2g, active: true };
    return json(res, 201, participantOut(u));
  }
  const patch = p.match(/^\/participants\/(\d+)$/);
  if (patch && m === "PATCH") {
    const u = auth(req);
    if (!u.participant || u.participant.id !== Number(patch[1])) throw new HttpError(404, "participant not found");
    const b = await readBody(req);
    for (const k of ["display_name", "feeder_node_id", "pv_capacity_kw", "battery_kwh", "ev_battery_kwh", "ev_max_power_kw", "ev_v2g", "active"]) if (b[k] !== undefined) u.participant[k] = b[k];
    return json(res, 200, participantOut(u));
  }

  // market
  if (p === "/intervals/current") return json(res, 200, publicInterval(current));
  const ivm = p.match(/^\/intervals\/(\d+)$/);
  if (ivm) {
    const iv = intervals.find((i) => i.id === Number(ivm[1]));
    if (!iv) throw new HttpError(404, "interval not found");
    return json(res, 200, publicInterval(iv));
  }
  if (p === "/price-history") return json(res, 200, priceHistory.slice(-Number(url.searchParams.get("limit") ?? 96)));
  if (p === "/orderbook") {
    const agg = (rows) => {
      const m = new Map();
      for (const r of rows) m.set(r.price_paise, (m.get(r.price_paise) ?? 0) + r.qty_wh);
      return [...m].map(([price_paise, qty_wh]) => ({ price_paise, qty_wh }));
    };
    return json(res, 200, { interval_id: current.id, supply_wh: botBook.supply_wh, demand_wh: botBook.demand_wh, bids: agg(botBook.bids), asks: agg(botBook.asks) });
  }
  if (p === "/positions" && m === "POST") {
    const u = auth(req);
    if (!u.participant) throw new HttpError(403, "no participant profile");
    const b = await readBody(req);
    if (b.interval_id !== current.id) throw new HttpError(409, "interval is not current");
    if (current.state !== "COMMIT") throw new HttpError(409, `commit window is ${current.state === "OPEN" ? "not open yet" : "closed"}`);
    if (positions.some((x) => x.address === u.address && x.interval_id === current.id)) throw new HttpError(409, "one position per interval");
    if (!["buy", "sell"].includes(b.side)) throw new HttpError(422, "side: invalid");
    if (!Number.isInteger(b.qty_wh) || b.qty_wh <= 0) throw new HttpError(422, "qty_wh: must be a positive integer");
    if (!Number.isInteger(b.limit_price_paise) || b.limit_price_paise < P_FIT || b.limit_price_paise > P_RET) throw new HttpError(422, "limit_price_paise: outside the tariff band");
    if (!/^0x[0-9a-f]{64}$/i.test(b.salt ?? "")) throw new HttpError(422, "salt: 32 bytes hex");
    const pos = { id: nextId++, address: u.address, interval_id: current.id, side: b.side, qty_wh: b.qty_wh, limit_price_paise: b.limit_price_paise, deadline: b.deadline ?? 0, salt: b.salt, commit_hash: commitHash(current.id, u.address, b.side, b.qty_wh, b.limit_price_paise, b.deadline ?? 0, b.salt), committed_tx: null, revealed: false, created_at: new Date().toISOString() };
    positions.push(pos);
    return json(res, 201, posOut(pos));
  }
  const rv = p.match(/^\/positions\/(\d+)\/reveal$/);
  if (rv && m === "POST") {
    const u = auth(req);
    const pos = positions.find((x) => x.id === Number(rv[1]) && x.address === u.address);
    if (!pos) throw new HttpError(404, "position not found");
    const iv = intervals.find((i) => i.id === pos.interval_id);
    if (!iv || iv.state !== "REVEAL") throw new HttpError(409, "reveal window is not open");
    const b = await readBody(req);
    const onchain = await onChainCommit(pos.interval_id, u.address);
    if (onchain === null && chainOk) throw new HttpError(409, "no on-chain commit found");
    if (onchain && onchain.toLowerCase() !== pos.commit_hash.toLowerCase()) throw new HttpError(409, "reveal does not match the on-chain commit");
    pos.revealed = true;
    pos.committed_tx = b.tx_hash ?? pos.committed_tx ?? "0x";
    return json(res, 200, posOut(pos));
  }
  if (p === "/positions/mine") {
    const u = auth(req);
    return json(res, 200, positions.filter((x) => x.address === u.address).map(posOut));
  }
  if (p === "/trades" && m === "GET") {
    const limit = Number(url.searchParams.get("limit") ?? 20);
    if (url.searchParams.get("mine") === "true") {
      const u = auth(req);
      return json(res, 200, trades.filter((t) => t.buyer === u.address || t.seller === u.address).slice(0, limit).map((t) => ({ ...t, side: t.buyer === u.address ? "buy" : "sell" })));
    }
    return json(res, 200, trades.slice(0, limit).map((t) => ({ ...t, side: null })));
  }
  const tm = p.match(/^\/trades\/(\d+)$/);
  if (tm) {
    const t = trades.find((x) => x.id === Number(tm[1]));
    if (!t) throw new HttpError(404, "trade not found");
    return json(res, 200, { ...t, side: null });
  }
  const rm = p.match(/^\/reputation\/(0x[0-9a-fA-F]{40})$/);
  if (rm) return json(res, 200, repOut(getAddress(rm[1])));
  if (p === "/grid/status") return json(res, 200, gridStatus());
  throw new HttpError(404, "not found");
}

function posOut(pos) {
  const { address, ...rest } = pos;
  return rest;
}

const server = http.createServer(async (req, res) => {
  try {
    await route(req, res);
  } catch (e) {
    if (e instanceof HttpError) return json(res, e.status, { detail: e.message });
    if (e instanceof SyntaxError) return json(res, 400, { detail: "invalid JSON" });
    console.error(e);
    json(res, 500, { detail: "internal error" });
  }
});

// ---- websocket ---------------------------------------------------------------------
const wss = new WebSocketServer({ server, path: "/ws" });
function broadcast(channel, type, data) {
  const msg = JSON.stringify({ channel, type, data });
  for (const c of wss.clients) if (c.readyState === 1) c.send(msg);
}
wss.on("connection", (ws) => {
  if (current) ws.send(JSON.stringify({ channel: "interval", type: "snapshot", data: publicInterval(current) }));
});

// ---- start ---------------------------------------------------------------------------
await probeChain();
newInterval();
setInterval(tick, 500);
server.listen(PORT, () => {
  console.log(`[mock] Phase 7 mock API on http://localhost:${PORT} (ws: /ws), interval ${INTERVAL_SECONDS}s, chain ${chainOk ? "connected" : "unreachable (chain-less mode)"}`);
});
