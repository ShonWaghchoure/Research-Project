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
import { concat, createPublicClient, createWalletClient, encodeAbiParameters, encodePacked, getAddress, http as viemHttp, keccak256, verifyMessage } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { hardhat } from "viem/chains";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT ?? 8001);
const INTERVAL_SECONDS = Number(process.env.MOCK_INTERVAL_SECONDS ?? 60);
const RPC_URL = process.env.RPC_URL ?? "http://127.0.0.1:8545";
const HARDHAT_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const OPERATOR_PK = process.env.OPERATOR_PRIVATE_KEY ?? HARDHAT_KEY_0;
// Security: this mock is a local development tool. By default it listens on loopback only,
// accepts browser requests only from the local frontend, and refuses to sign with the
// public Hardhat key against anything but a local node.
const HOST = process.env.MOCK_HOST ?? "127.0.0.1";
const DEV_LOGIN = process.env.MOCK_DEV_LOGIN === "1";
const CORS_ORIGINS = (process.env.MOCK_CORS_ORIGINS ?? "http://localhost:3000,http://127.0.0.1:3000").split(",").map((o) => o.trim()).filter(Boolean);
const TOKEN_TTL_MS = 60 * 60 * 1000;
const NONCE_TTL_MS = 5 * 60 * 1000;
const MAX_USERS = 10_000;
const MAX_TOKENS = 10_000;
const MAX_BODY_BYTES = 64 * 1024;
if (OPERATOR_PK.toLowerCase() === HARDHAT_KEY_0 && !/^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(RPC_URL)) {
  console.error("[mock] refusing to use the public Hardhat key against a non-local RPC; set OPERATOR_PRIVATE_KEY");
  process.exit(1);
}

const deployments = JSON.parse(readFileSync(path.join(__dirname, "..", "src", "contracts", "localhost.json"), "utf8"));
const SETTLEMENT = deployments.contracts.Settlement;
const ANCHOR = deployments.contracts.ReputationAnchor;

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
const tokens = new Map(); // token -> { address, exp }

function issueToken(address) {
  if (tokens.size >= MAX_TOKENS) tokens.delete(tokens.keys().next().value); // evict oldest
  const tok = `mock.${randomBytes(24).toString("hex")}`;
  tokens.set(tok, { address, exp: Date.now() + TOKEN_TTL_MS });
  return tok;
}
const positions = []; // user positions
const trades = [];
const priceHistory = [];
const reputations = new Map(); // address -> { alpha, beta, evidence }
/** @type {Map<string, object[]>} address -> history points */
const reputationHistory = new Map();
/** @type {Map<string, object>} `${intervalId}:${addressLower}` -> score row with leaf/proof inputs */
const reputationScores = new Map();
/** @type {Map<number, string>} intervalId -> merkle root */
const reputationRoots = new Map();
/** @type {object[]} fairness metric rows for B2 and B3 */
const fairnessHistory = [];
let intervals = [];
let current = null;
let nextIntervalId = Number(process.env.MOCK_FIRST_INTERVAL ?? Math.floor(Date.now() / 1000) % 100000);
let nextId = 1;
let prevPRef = null;

// Phase 10 mock state
const HARDHAT_ADMIN = getAddress("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266");
const configValues = {
  p_fit: 300,
  p_ret: 800,
  k: 2,
  alpha: 0.7,
  c: 3,
  r_ref: 0.8,
  rho_min: 0.3,
  r_cap: 0.9,
  beta: 25,
  w_del: 0.45,
  w_rev: 0.15,
  w_hon: 0.2,
  w_col: 0.2,
  half_life_intervals: 672,
};
/** @type {object[]} */
const flags = [];
/** @type {object[]} */
const auditLog = [];
/** @type {object[]} */
const attackRuns = [];
let nextFlagId = 1;
let nextAttackId = 1;
let nextAuditLogId = 1;
let simRunning = true;
let simIntervalSeconds = INTERVAL_SECONDS;
/** @type {number | null} */
let demoAuditIntervalId = null;

const NODES = ["n0", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "n10", "n11", "n12"];
const FEEDER_NODES = NODES.slice(1); // participants sit on n1..n12; n0 is the transformer
const LINES = [["n0", "n1"], ["n0", "n2"], ["n0", "n3"], ["n1", "n4"], ["n1", "n5"], ["n1", "n6"], ["n2", "n7"], ["n3", "n8"], ["n3", "n9"], ["n7", "n10"], ["n10", "n11"], ["n10", "n12"]];

function pseudo(i) {
  return getAddress(`0x${keccak256(encodeAbiParameters([{ type: "uint256" }], [BigInt(1000 + i)])).slice(26)}`);
}
const BOTS = Array.from({ length: 24 }, (_, i) => ({ address: pseudo(i), node: FEEDER_NODES[i % FEEDER_NODES.length], seller: i % 3 !== 0 }));

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
  // Give bots a quiet evidence bump so the Merkle tree always has many leaves.
  for (const b of BOTS) {
    const r = rep(b.address);
    r.alpha += 0.4;
    r.evidence += 1;
  }
  for (const u of users.values()) {
    if (!u.participant) continue;
    const r = rep(u.address);
    if (r.evidence === 0) {
      r.alpha += 0.5;
      r.evidence += 1;
    }
  }
  anchorReputation(iv).catch((e) => console.warn(`[mock] reputation anchor failed: ${String(e.shortMessage ?? e.message).split("\n")[0]}`));
  pushFairness(iv);
}

function reputationLeaf(address, scoreBp, evidenceCount) {
  return keccak256(encodePacked(["address", "uint16", "uint32"], [getAddress(address), scoreBp, evidenceCount]));
}

function hashPair(a, b) {
  const [left, right] = BigInt(a) <= BigInt(b) ? [a, b] : [b, a];
  return keccak256(concat([left, right]));
}

function buildMerkle(leaves) {
  if (!leaves.length) throw new Error("no leaves");
  let layer = [...leaves];
  const layers = [layer];
  while (layer.length > 1) {
    const next = [];
    for (let i = 0; i < layer.length; i += 2) {
      if (i + 1 === layer.length) next.push(layer[i]);
      else next.push(hashPair(layer[i], layer[i + 1]));
    }
    layer = next;
    layers.push(layer);
  }
  return { root: layers[layers.length - 1][0], layers, leaves };
}

function merkleProof(leaves, index) {
  const tree = buildMerkle(leaves);
  const proof = [];
  let idx = index;
  for (const layer of tree.layers.slice(0, -1)) {
    const pair = idx ^ 1;
    if (pair < layer.length) proof.push(layer[pair]);
    idx = Math.floor(idx / 2);
  }
  return { proof, root: tree.root };
}

async function postRootOnChain(intervalId, root) {
  if (!(await probeChain())) return false;
  try {
    const hash = await walletClient.writeContract({
      address: ANCHOR.address,
      abi: ANCHOR.abi,
      functionName: "postRoot",
      args: [BigInt(intervalId), root],
    });
    await publicClient.waitForTransactionReceipt({ hash });
    return true;
  } catch (e) {
    console.warn(`[mock] postRoot(${intervalId}) failed: ${String(e.shortMessage ?? e.message).split("\n")[0]}`);
    return false;
  }
}

async function anchorReputation(iv) {
  const addresses = [
    ...new Set([
      ...BOTS.map((b) => b.address),
      ...DEMO_ACCOUNTS,
      ...[...users.values()].filter((u) => u.participant).map((u) => u.address),
    ]),
  ]
    .map((a) => getAddress(a))
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  const rows = addresses.map((address) => {
    const out = repOut(address);
    const score_bp = Math.max(0, Math.min(10_000, Math.round(out.score * 10_000)));
    const leaf_hash = reputationLeaf(address, score_bp, out.evidence_count);
    return { address, score_bp, evidence_count: out.evidence_count, leaf_hash, out };
  });
  const leaves = rows.map((r) => r.leaf_hash);
  const { root } = buildMerkle(leaves);
  reputationRoots.set(iv.id, root);
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const key = `${iv.id}:${row.address.toLowerCase()}`;
    reputationScores.set(key, {
      address: row.address,
      interval_id: iv.id,
      score_bp: row.score_bp,
      evidence_count: row.evidence_count,
      leaf_hash: row.leaf_hash,
      leaf_index: i,
      leaves,
    });
    const hist = reputationHistory.get(row.address.toLowerCase()) ?? [];
    hist.push({
      interval_id: iv.id,
      ends_at: iv.ends_at,
      score: row.out.score,
      score_bp: row.score_bp,
      tier: row.out.tier,
      evidence_count: row.evidence_count,
      components: row.out.components,
    });
    if (hist.length > 200) hist.shift();
    reputationHistory.set(row.address.toLowerCase(), hist);
  }
  await postRootOnChain(iv.id, root);
}

function pushFairness(iv) {
  const r = mulberry32(iv.id * 19);
  const base = {
    interval_id: iv.id,
    ends_at: iv.ends_at,
    jain: Number((0.72 + r() * 0.22).toFixed(3)),
    gini: Number((0.12 + r() * 0.18).toFixed(3)),
    hhi: Number((0.08 + r() * 0.12).toFixed(3)),
    small_actor_parity: Number((0.85 + r() * 0.25).toFixed(3)),
    price_impact: Number((0.01 + r() * 0.04).toFixed(4)),
    welfare_efficiency: Number((0.88 + r() * 0.1).toFixed(3)),
  };
  // B2 (SDR + proportional, no reputation/grid) is slightly less fair / efficient.
  fairnessHistory.push({
    ...base,
    baseline: "B3",
  });
  fairnessHistory.push({
    interval_id: iv.id,
    ends_at: iv.ends_at,
    baseline: "B2",
    jain: Number(Math.max(0.4, base.jain - 0.08 - r() * 0.06).toFixed(3)),
    gini: Number(Math.min(0.6, base.gini + 0.06 + r() * 0.05).toFixed(3)),
    hhi: Number(Math.min(0.4, base.hhi + 0.04 + r() * 0.04).toFixed(3)),
    small_actor_parity: Number(Math.max(0.4, base.small_actor_parity - 0.12 - r() * 0.08).toFixed(3)),
    price_impact: Number((base.price_impact + 0.01 + r() * 0.02).toFixed(4)),
    welfare_efficiency: Number(Math.max(0.6, base.welfare_efficiency - 0.05 - r() * 0.05).toFixed(3)),
  });
  if (fairnessHistory.length > 800) fairnessHistory.splice(0, fairnessHistory.length - 800);
}

/** Well-known Hardhat accounts #1–#4 so demo wallets have reputation history. */
const DEMO_ACCOUNTS = [
  "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
  "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
  "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",
];

function seedHistory() {
  const start = Date.now() - 48 * INTERVAL_SECONDS * 1000;
  for (let i = 0; i < 48; i++) {
    const r = mulberry32(1000 + i);
    const sdr = Number((0.6 + r() * 1.6).toFixed(4));
    const p = referencePrice(sdr);
    prevPRef = p;
    const ends = new Date(start + (i + 1) * INTERVAL_SECONDS * 1000).toISOString();
    priceHistory.push({ interval_id: nextIntervalId - 48 + i, ends_at: ends, p_ref_paise: p, sdr });
    const ivLike = { id: nextIntervalId - 48 + i, ends_at: ends };
    pushFairness(ivLike);
  }
  // Warm demo wallets so the Reputation page is not empty on first connect.
  for (const a of DEMO_ACCOUNTS) {
    const r = rep(a);
    r.alpha = 12;
    r.beta = 4;
    r.evidence = 40;
    r.reveal = 1;
    r.honesty = 0.95;
    r.collusion = 0.05;
    const hist = [];
    for (let i = 0; i < 48; i++) {
      const rr = mulberry32(2000 + DEMO_ACCOUNTS.indexOf(a) * 100 + i);
      const score = Number((0.35 + (i / 48) * 0.4 + rr() * 0.05).toFixed(3));
      const ends = new Date(start + (i + 1) * INTERVAL_SECONDS * 1000).toISOString();
      hist.push({
        interval_id: nextIntervalId - 48 + i,
        ends_at: ends,
        score,
        score_bp: Math.round(score * 10_000),
        tier: score >= 0.8 ? "trusted" : score >= 0.5 ? "standard" : "probation",
        evidence_count: Math.min(100, 5 + i),
        components: {
          delivery: Number((0.6 + i / 80).toFixed(3)),
          reveal: 1,
          honesty: 0.95,
          collusion: 0.05,
        },
      });
    }
    reputationHistory.set(a.toLowerCase(), hist);
  }
}

async function seedReputationProof() {
  const seedIv = { id: nextIntervalId - 1, ends_at: new Date().toISOString() };
  await anchorReputation(seedIv);
}

function gridStatus() {
  const r = mulberry32((current?.id ?? 1) * 13);
  const lines = LINES.map(([a, b]) => ({ id: `l_${a}_${b}`, from_node: a, to_node: b, capacity_kw: 100, loading_pct: Number((15 + r() * 60).toFixed(1)) }));
  const congested = lines.filter((l) => l.loading_pct > 70).map((l) => l.id);
  const byNode = Object.fromEntries(FEEDER_NODES.map((n) => [n, []]));
  for (const b of BOTS) byNode[b.node].push({ address: b.address, kind: b.seller ? "prosumer" : "consumer" });
  for (const u of users.values()) {
    if (!u.participant) continue;
    const node = u.participant.feeder_node_id || FEEDER_NODES[u.id % FEEDER_NODES.length];
    if (!byNode[node]) byNode[node] = [];
    byNode[node].push({ address: u.address, kind: u.participant.type ?? "consumer" });
  }
  return {
    interval_id: current?.id ?? 0,
    lines,
    congested_line_ids: congested,
    max_loading_pct: Math.max(...lines.map((l) => l.loading_pct)),
    p2p_share_pct: Number((55 + r() * 20).toFixed(1)),
    nodes: [
      { id: "n0", label: "Transformer", kind: "root", participants: [] },
      ...FEEDER_NODES.map((id) => ({ id, label: id.toUpperCase(), kind: "feeder", participants: byNode[id] ?? [] })),
    ],
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
  const headers = { "Content-Type": "application/json", "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,OPTIONS", Vary: "Origin" };
  if (res.corsOrigin) headers["Access-Control-Allow-Origin"] = res.corsOrigin;
  res.writeHead(status, headers);
  res.end(body === undefined ? "" : JSON.stringify(body));
}

function auth(req) {
  const h = req.headers.authorization ?? "";
  const tok = h.startsWith("Bearer ") ? h.slice(7) : null;
  const entry = tok && tokens.get(tok);
  if (!entry || entry.exp < Date.now()) {
    if (entry) tokens.delete(tok);
    throw new HttpError(401, "not authenticated");
  }
  return users.get(entry.address);
}

function requireAdmin(req) {
  const u = auth(req);
  if (u.role !== "admin") throw new HttpError(403, "insufficient role");
  return u;
}

function requireOperator(req) {
  const u = auth(req);
  if (u.role !== "admin" && u.role !== "operator") throw new HttpError(403, "insufficient role");
  return u;
}

function pushAudit(actor, action, resourceType, resourceId, before, after) {
  auditLog.unshift({
    id: nextAuditLogId++,
    actor_user_id: actor?.id ?? null,
    action,
    resource_type: resourceType,
    resource_id: resourceId == null ? null : String(resourceId),
    before,
    after,
    ip: "127.0.0.1",
    created_at: new Date().toISOString(),
  });
  if (auditLog.length > 200) auditLog.pop();
}

function hashTriple(stored, recomputed = stored, onChain = null) {
  const s = stored ? String(stored).toLowerCase() : null;
  const r = recomputed ? String(recomputed).toLowerCase() : null;
  const o = onChain ? String(onChain).toLowerCase() : null;
  return {
    stored: s,
    recomputed: r,
    on_chain: o,
    stored_matches_recomputed: s && r ? s === r : null,
    stored_matches_on_chain: s && o ? s === o : null,
    recomputed_matches_on_chain: r && o ? r === o : null,
  };
}

function mockAttackSeries(defensesOn) {
  const series = [];
  for (let i = 0; i < 12; i++) {
    const attackBoost = defensesOn ? 0 : 40 + i * 2;
    series.push({
      interval: i,
      p_ref: 500 + attackBoost + (i % 3) * 5,
      sdr: Number((0.8 + i * 0.02).toFixed(3)),
      jain: defensesOn ? 0.85 - i * 0.005 : 0.55 - i * 0.01,
      gini: defensesOn ? 0.2 + i * 0.005 : 0.45 + i * 0.01,
      hhi: defensesOn ? 0.12 : 0.28,
      mean_reputation: defensesOn ? 0.7 : 0.45,
    });
  }
  return series;
}

function seedPhase10() {
  const demoRoot = keccak256(encodeAbiParameters([{ type: "string" }], ["audit-demo"]));
  const demoIv = {
    id: Math.max(1, nextIntervalId - 100),
    state: "METERED",
    starts_at: new Date(Date.now() - 3600_000).toISOString(),
    ends_at: new Date(Date.now() - 2700_000).toISOString(),
    commit_deadline: new Date(Date.now() - 3300_000).toISOString(),
    reveal_deadline: new Date(Date.now() - 3000_000).toISOString(),
    p_ref_paise: 520,
    prev_p_ref_paise: 500,
    sdr: 1.1,
    active_participants: 2,
    input_root: demoRoot,
    result_hash: keccak256(encodeAbiParameters([{ type: "string" }], ["audit-result"])),
    engine_version: "mock-phase10",
    on_chain: false,
  };
  intervals.push(demoIv);
  demoAuditIntervalId = demoIv.id;
  flags.push({
    id: nextFlagId++,
    participant_id: 1,
    interval_id: demoIv.id,
    kind: "collusion",
    severity: "medium",
    status: "open",
    detail: { score: 0.72, note: "mock sliding-window flag" },
    created_at: new Date().toISOString(),
    resolved_at: null,
    resolved_by: null,
  });
}

async function readBody(req) {
  // Count bytes while streaming: buffering first would let one huge POST exhaust memory.
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > MAX_BODY_BYTES) {
      req.destroy();
      throw new HttpError(413, "request too large");
    }
    chunks.push(c);
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

async function route(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const p = url.pathname;
  const m = req.method;

  if (m === "OPTIONS") return json(res, 204);
  if (p === "/health") return json(res, 200, { status: "ok", postgres: "mock", redis: "mock", chain_rpc: chainOk ? "ok" : "down", block_number: chainOk ? Number(await publicClient.getBlockNumber()) : null, chain_id: 31337, demo_audit_interval_id: demoAuditIntervalId, simulation_running: simRunning, interval_seconds: simIntervalSeconds });
  if (p === "/docs") { res.writeHead(200, { "Content-Type": "text/plain" }); return res.end("Mock Phase 7 API. See frontend/mock/server.mjs."); }

  // auth
  if (p === "/auth/nonce" && m === "POST") {
    const { address } = await readBody(req);
    let addr;
    try { addr = getAddress(address); } catch { throw new HttpError(422, "invalid address"); }
    if (!users.has(addr) && users.size >= MAX_USERS) throw new HttpError(503, "too many users");
    if (!users.has(addr)) {
      const role = addr === HARDHAT_ADMIN ? "admin" : "participant";
      users.set(addr, { id: users.size + 1, address: addr, role, participant: null });
    }
    const u = users.get(addr);
    u.nonce = randomBytes(16).toString("hex");
    u.nonceUsed = false;
    u.nonceIssued = Date.now();
    u.message = siweMessage(addr, u.nonce);
    return json(res, 200, { address: addr, nonce: u.nonce, message: u.message, chain_id: 31337 });
  }
  // Mock-only helper for Playwright: mint an admin JWT without a wallet signature.
  if (p === "/auth/dev-login" && m === "POST") {
    if (!DEV_LOGIN) throw new HttpError(404, "not found"); // only with MOCK_DEV_LOGIN=1 (tests)
    const body = await readBody(req);
    const role = body.role === "operator" ? "operator" : "admin";
    let addr = HARDHAT_ADMIN;
    if (body.address) {
      try { addr = getAddress(body.address); } catch { throw new HttpError(422, "invalid address"); }
    }
    if (!users.has(addr)) users.set(addr, { id: users.size + 1, address: addr, role, participant: null });
    const u = users.get(addr);
    u.role = role;
    return json(res, 200, { access_token: issueToken(addr), token_type: "bearer", role: u.role, address: addr });
  }
  if (p === "/auth/verify" && m === "POST") {
    const { address, message, signature } = await readBody(req);
    const addr = getAddress(address);
    const u = users.get(addr);
    if (!u || !u.nonce || u.nonceUsed) throw new HttpError(401, "nonce required");
    // Same rule as the backend: only the exact message issued, before it expires.
    if (Date.now() - (u.nonceIssued ?? 0) > NONCE_TTL_MS) throw new HttpError(401, "sign-in message expired, request a new one");
    if (message !== u.message) throw new HttpError(401, "message does not match the one issued");
    const ok = await verifyMessage({ address: addr, message, signature });
    if (!ok) throw new HttpError(401, "signature does not match address");
    u.nonceUsed = true;
    return json(res, 200, { access_token: issueToken(addr), token_type: "bearer", role: u.role, address: addr });
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
  // Same protocol as the backend: the client reports its commit tx, the server checks it on chain.
  const cm = p.match(/^\/positions\/(\d+)\/commit$/);
  if (cm && m === "POST") {
    const u = auth(req);
    const pos = positions.find((x) => x.id === Number(cm[1]) && x.address === u.address);
    if (!pos) throw new HttpError(404, "position not found");
    const b = await readBody(req);
    if (!/^0x[0-9a-fA-F]{64}$/.test(b.tx_hash ?? "")) throw new HttpError(422, "tx_hash: 32 bytes hex");
    if (!chainOk) throw new HttpError(503, "chain RPC is unavailable");
    const onchain = await onChainCommit(pos.interval_id, u.address);
    if (!onchain) throw new HttpError(409, "on-chain commit not found");
    if (onchain.toLowerCase() !== pos.commit_hash.toLowerCase()) throw new HttpError(409, "on-chain commit does not match position");
    pos.committed_tx = b.tx_hash;
    return json(res, 200, posOut(pos));
  }
  const rv = p.match(/^\/positions\/(\d+)\/reveal$/);
  if (rv && m === "POST") {
    const u = auth(req);
    const pos = positions.find((x) => x.id === Number(rv[1]) && x.address === u.address);
    if (!pos) throw new HttpError(404, "position not found");
    const iv = intervals.find((i) => i.id === pos.interval_id);
    if (!iv || iv.state !== "REVEAL") throw new HttpError(409, "reveal window is not open");
    const b = await readBody(req);
    if (!pos.committed_tx) throw new HttpError(409, "on-chain commit confirmation is required");
    if ((b.tx_hash ?? "").toLowerCase() !== pos.committed_tx.toLowerCase()) throw new HttpError(409, "commit transaction hash mismatch");
    if (!chainOk) throw new HttpError(503, "chain RPC is unavailable");
    const onchain = await onChainCommit(pos.interval_id, u.address);
    if (!onchain || onchain.toLowerCase() !== pos.commit_hash.toLowerCase()) throw new HttpError(409, "on-chain commit does not match position");
    pos.revealed = true;
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
  const rh = p.match(/^\/reputation\/(0x[0-9a-fA-F]{40})\/history$/);
  if (rh) {
    const address = getAddress(rh[1]);
    const history = reputationHistory.get(address.toLowerCase()) ?? [];
    return json(res, 200, { address, history });
  }
  const rp = p.match(/^\/reputation\/(0x[0-9a-fA-F]{40})\/proof$/);
  if (rp) {
    const address = getAddress(rp[1]);
    const intervalId = Number(url.searchParams.get("interval_id"));
    if (!Number.isInteger(intervalId)) throw new HttpError(422, "interval_id: required integer");
    const row = reputationScores.get(`${intervalId}:${address.toLowerCase()}`);
    if (!row) throw new HttpError(404, "score not found for interval");
    const { proof, root } = merkleProof(row.leaves, row.leaf_index);
    return json(res, 200, {
      address,
      interval_id: intervalId,
      score_bp: row.score_bp,
      evidence_count: row.evidence_count,
      leaf_hash: row.leaf_hash,
      proof,
      root,
    });
  }
  const rm = p.match(/^\/reputation\/(0x[0-9a-fA-F]{40})$/);
  if (rm) return json(res, 200, repOut(getAddress(rm[1])));
  if (p === "/grid/status") return json(res, 200, gridStatus());
  if (p === "/fairness/history") {
    const baseline = (url.searchParams.get("baseline") ?? "B3").toUpperCase();
    if (baseline !== "B2" && baseline !== "B3") throw new HttpError(422, "baseline: must be B2 or B3");
    const limit = Number(url.searchParams.get("limit") ?? 96);
    const rows = fairnessHistory.filter((f) => f.baseline === baseline).slice(-limit);
    return json(res, 200, { baseline, metrics: rows });
  }

  // ---- Phase 10: audit / admin / attacks ------------------------------------
  const auditGet = p.match(/^\/audit\/(\d+)$/);
  if (auditGet && m === "GET") {
    const id = Number(auditGet[1]);
    const iv = intervals.find((i) => i.id === id);
    if (!iv) throw new HttpError(404, "interval not found");
    const leaves = [
      { participant_id: 1, side: "buy", qty_kwh: 2, limit_price: 800, leaf: iv.input_root },
      { participant_id: 2, side: "sell", qty_kwh: 2, limit_price: 300, leaf: iv.result_hash },
    ];
    return json(res, 200, {
      interval_id: iv.id,
      state: iv.state,
      engine_version: iv.engine_version ?? "mock-phase10",
      p_ref_paise: iv.p_ref_paise,
      sdr: iv.sdr,
      positions: leaves.map((l) => ({
        participant_id: l.participant_id,
        side: l.side,
        qty_wh: Math.round(l.qty_kwh * 1000),
        limit_price_paise: l.limit_price,
        revealed: true,
      })),
      trades: [{ buyer_id: 1, seller_id: 2, qty_wh: 2000, price_paise: iv.p_ref_paise ?? 520 }],
      input_root: hashTriple(iv.input_root),
      result_hash: hashTriple(iv.result_hash, null, null),
      merkle_leaves: leaves,
      explorer: {
        network: "localhost",
        settlement: SETTLEMENT.address,
        interval_hint: `Settlement.intervals(${iv.id})`,
        block_explorer: null,
      },
    });
  }
  const auditRerun = p.match(/^\/audit\/(\d+)\/rerun$/);
  if (auditRerun && m === "POST") {
    requireOperator(req);
    const id = Number(auditRerun[1]);
    const iv = intervals.find((i) => i.id === id);
    if (!iv) throw new HttpError(404, "interval not found");
    if (!iv.result_hash) throw new HttpError(400, "interval has not been cleared yet");
    const input = hashTriple(iv.input_root, iv.input_root, null);
    const result = hashTriple(iv.result_hash, iv.result_hash, null);
    return json(res, 200, {
      interval_id: iv.id,
      engine_version_stored: iv.engine_version ?? "mock-phase10",
      engine_version_now: "mock-phase10",
      input_root: input,
      result_hash: result,
      match: true,
      note: "",
    });
  }

  if (p === "/admin/config" && m === "GET") {
    requireAdmin(req);
    return json(res, 200, { values: { ...configValues } });
  }
  if (p === "/admin/config" && m === "PUT") {
    const u = requireAdmin(req);
    const body = await readBody(req);
    const updates = body.values ?? {};
    const before = {};
    const after = {};
    for (const [k, v] of Object.entries(updates)) {
      before[k] = configValues[k] ?? null;
      configValues[k] = v;
      after[k] = v;
    }
    pushAudit(u, "config.update", "config", Object.keys(after).join(","), before, after);
    return json(res, 200, { values: { ...configValues } });
  }

  if (p === "/admin/flags" && m === "GET") {
    requireAdmin(req);
    const status = url.searchParams.get("status") ?? "open";
    const rows = flags.filter((f) => !status || f.status === status);
    return json(res, 200, rows);
  }
  const flagResolve = p.match(/^\/admin\/flags\/(\d+)\/resolve$/);
  if (flagResolve && m === "POST") {
    const u = requireAdmin(req);
    const flag = flags.find((f) => f.id === Number(flagResolve[1]));
    if (!flag) throw new HttpError(404, "flag not found");
    if (flag.status !== "open") throw new HttpError(400, "flag already resolved");
    const body = await readBody(req);
    if (!["resolved", "dismissed"].includes(body.status)) throw new HttpError(422, "status: invalid");
    const before = { status: flag.status };
    flag.status = body.status;
    flag.resolved_at = new Date().toISOString();
    flag.resolved_by = u.id;
    if (body.note) flag.detail = { ...flag.detail, resolve_note: body.note };
    pushAudit(u, "flag.resolve", "flag", flag.id, before, { status: flag.status, note: body.note ?? null });
    return json(res, 200, flag);
  }

  if (p === "/admin/attacks/run" && m === "POST") {
    const u = requireAdmin(req);
    const body = await readBody(req);
    const scenario = body.scenario;
    const allowed = ["sybil_farm", "collusion_ring", "price_manipulation", "false_reports", "defect_after_trust"];
    if (!allowed.includes(scenario)) throw new HttpError(400, `unknown scenario: ${scenario}`);
    const defensesOn = body.defenses === "on";
    const series = mockAttackSeries(defensesOn);
    const attacker_profit_paise = defensesOn ? 1200 : 48_000;
    const plain_summary = defensesOn
      ? `${scenario}: defenses on — attacker profit collapsed; median cap / reputation weighting limited impact.`
      : `${scenario}: defenses off — attacker extracted ${attacker_profit_paise} paise of surplus.`;
    const params = {
      participants: Number(body.params?.participants ?? 40),
      days: Number(body.params?.days ?? 1),
      seed: Number(body.params?.seed ?? 42),
      max_intervals: Number(body.params?.max_intervals ?? 24),
    };
    const row = {
      id: nextAttackId++,
      scenario,
      defenses: defensesOn,
      params,
      status: "completed",
      summary: { market: { welfare: 1 }, attacker_profit_paise },
      series,
      attacker_profit_paise,
      plain_summary,
      created_at: new Date().toISOString(),
    };
    attackRuns.push(row);
    pushAudit(u, "attack.run", "attack_run", scenario, null, { scenario, defenses: defensesOn, params });
    return json(res, 200, row);
  }

  if (p === "/admin/simulation" && m === "GET") {
    requireAdmin(req);
    return json(res, 200, {
      running: simRunning,
      interval_seconds: simIntervalSeconds,
      override_active: simIntervalSeconds !== INTERVAL_SECONDS,
    });
  }
  if (p === "/admin/simulation/start" && m === "POST") {
    const u = requireAdmin(req);
    simRunning = true;
    const state = { running: simRunning, interval_seconds: simIntervalSeconds, override_active: simIntervalSeconds !== INTERVAL_SECONDS };
    pushAudit(u, "simulation.start", "simulation", "live", null, state);
    return json(res, 200, state);
  }
  if (p === "/admin/simulation/stop" && m === "POST") {
    const u = requireAdmin(req);
    simRunning = false;
    const state = { running: simRunning, interval_seconds: simIntervalSeconds, override_active: simIntervalSeconds !== INTERVAL_SECONDS };
    pushAudit(u, "simulation.stop", "simulation", "live", null, state);
    return json(res, 200, state);
  }
  if (p === "/admin/simulation/speed" && m === "PUT") {
    const u = requireAdmin(req);
    const body = await readBody(req);
    const sec = Number(body.interval_seconds);
    if (!Number.isInteger(sec) || sec < 5 || sec > 3600) throw new HttpError(400, "interval_seconds out of range");
    const before = { running: simRunning, interval_seconds: simIntervalSeconds, override_active: simIntervalSeconds !== INTERVAL_SECONDS };
    simIntervalSeconds = sec;
    const state = { running: simRunning, interval_seconds: simIntervalSeconds, override_active: true };
    pushAudit(u, "simulation.speed", "simulation", "live", before, state);
    return json(res, 200, state);
  }

  if (p === "/admin/audit-log" && m === "GET") {
    requireAdmin(req);
    const limit = Number(url.searchParams.get("limit") ?? 100);
    return json(res, 200, auditLog.slice(0, limit));
  }

  throw new HttpError(404, "not found");
}

function posOut(pos) {
  const { address, ...rest } = pos;
  return rest;
}

const server = http.createServer(async (req, res) => {
  const origin = req.headers.origin;
  if (origin && CORS_ORIGINS.includes(origin)) res.corsOrigin = origin;
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
const wss = new WebSocketServer({
  server,
  path: "/ws",
  maxPayload: 4 * 1024,
  // Browsers always send Origin; refuse other sites. Non-browser clients (tests) send none.
  verifyClient: ({ origin }) => !origin || CORS_ORIGINS.includes(origin),
});
function broadcast(channel, type, data) {
  const msg = JSON.stringify({ channel, type, data });
  for (const c of wss.clients) if (c.readyState === 1) c.send(msg);
}
wss.on("connection", (ws) => {
  if (current) ws.send(JSON.stringify({ channel: "interval", type: "snapshot", data: publicInterval(current) }));
});

// ---- start ---------------------------------------------------------------------------
await probeChain();
seedHistory();
seedPhase10();
await seedReputationProof();
newInterval();
setInterval(tick, 500);
server.listen(PORT, HOST, () => {
  console.log(`[mock] Phase 7/9/10 mock API on http://${HOST}:${PORT} (ws: /ws), interval ${INTERVAL_SECONDS}s, chain ${chainOk ? "connected" : "unreachable (chain-less mode)"}`);
});
