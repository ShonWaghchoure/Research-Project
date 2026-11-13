# Fair and Trustworthy P2P Energy Trading (Smart Grid 2.0)

A web app that runs a simulated 15-minute peer-to-peer energy market:
SDR-based pricing, reputation-gated and grid-aware matching, commit-reveal bidding,
on-chain escrow and settlement, and a manipulation-resistant reputation system.

This README is the build script. It is split into 13 phases (0 to 12). Each phase has a
ready-to-paste prompt for an AI coding agent, plus acceptance checks. Do the phases in order and
do not start a phase until the previous one passes its checks.

---

## How to use this file

1. Create the repo, put this README at the root, and create the agent instruction file below
   (name it CLAUDE.md, GEMINI.md, AGENTS.md or whatever your agent reads).
2. For each phase: paste the prompt, let the agent work, run the acceptance checks yourself,
   then commit (`git commit -m "phase N: ..."`). Only then move on.
3. If a phase fails its checks, use a repair prompt (see the end) instead of starting over.
4. Read the contract code and the math code yourself. Agents make subtle mistakes there.
5. If the agent hits a usage limit, stop at a green commit and resume the next day with:
   "Read README.md and the repo. We are on Phase N. Continue."

### Agent instruction file (paste into CLAUDE.md / GEMINI.md / AGENTS.md)

```text
PROJECT: Fair and Trustworthy P2P energy trading simulator (web app).
STACK: Contracts = Solidity + Hardhat (TypeScript tests) + OpenZeppelin.
       Backend = Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL, Redis, web3.py,
       numpy, scipy, cvxpy, pandas, networkx, scikit-learn, pytest, Hypothesis, ruff, mypy.
       Frontend = Next.js (App Router), TypeScript, Tailwind, shadcn/ui, wagmi + viem,
       TanStack Query, Zustand, Zod, Recharts, Framer Motion.
LAYOUT: contracts/  backend/app/{api,core,db,engine,reputation,sim,chain,workers}  backend/tests
        frontend/  docs/  docker-compose.yml  Makefile  .env.example
RULES:
 1. backend/app/engine and backend/app/reputation contain PURE functions: data in, data out.
    No database, no network, no clock, no random without an explicit seed argument.
 2. Money and energy are integers at every boundary: energy in Wh, price in paise per kWh
    (INR 3 = 300 paise, INR 8 = 800 paise). Floats are allowed only inside the solver and the
    reputation math, and results are rounded before they leave a function.
 3. Every function you write gets unit tests. Run the tests before saying you are done.
 4. Never commit secrets. Keep .env out of git. Use testnet keys only.
 5. Do not change files outside the scope of the current phase unless required, and say so.
 6. When finished, print: what you built, the commands to run it, and the test results.
 7. If something in the spec is ambiguous, pick the simplest option, write it in docs/DECISIONS.md,
    and continue. Do not stop to ask unless you are blocked.
```

### Global parameters (keep in backend/app/core/params.py and the config table)

```text
p_fit = 300 paise/kWh, p_ret = 800 paise/kWh, interval = 15 min (900 s; demo mode 30-60 s)
k = 2, alpha = 0.7, c = 3, R_ref = 0.8, rho_min = 0.3, R_cap = 0.9, beta <= 5% of (p_ret - p_fit)
score weights (w_del, w_rev, w_hon, w_col) = (0.45, 0.15, 0.20, 0.20)
Beta prior (alpha0, beta0) = (1, 2), kappa = 3, z = 1, half-life H = 672 intervals
shortfall penalty f = 0.1, collusion window = 96 intervals
```

---

## Phase map

| Phase | Name | Layer | Output |
| --- | --- | --- | --- |
| 0 | Walking skeleton | Everything | One command starts all; browser shows block number via backend |
| 1 | Pricing engine | Engine | SDR price with manipulation limits, tested |
| 2 | Matching and clearing engine | Engine | QP matching, grid limits, EV, deterministic hashes |
| 3 | Reputation, defenses, fairness | Engine | Reputation math, Sybil and collusion detection, fairness metrics |
| 4 | Simulator and baselines | Simulation | Headless CLI that runs markets with bots and baselines B0 to B3 |
| 5 | Smart contracts | Chain | Four contracts, full tests, deploy script |
| 6 | Backend foundation | Backend | Database, auth, participants, config, audit log |
| 7 | Market lifecycle | Backend and chain | Interval state machine, clearing, settlement, metering, reputation anchoring, WebSocket |
| 8 | Frontend foundation | Frontend | Design system, onboarding, dashboard, trade flow |
| 9 | Frontend market views | Frontend | Market, grid map, reputation, fairness lab |
| 10 | Attack lab, audit, admin | Full stack | Scenario runner, audit re-run, admin console, detection jobs wired in |
| 11 | Experiments | Research | E1 to E10 results, figures, ablations |
| 12 | Hardening, deploy, docs | Everything | Security pass, Sepolia deploy, demo script, final docs |

---

## Phase 0: Walking skeleton

Goal: one command starts everything, and the browser shows the current block number read from the
local chain through the backend. No market logic yet.

```text
Read the instruction file. Create the monorepo layout described there.
1. contracts/: Hardhat TypeScript project, OpenZeppelin installed. Add a trivial Ping contract
   and a deploy script that writes addresses to contracts/deployments/<network>.json.
2. backend/: FastAPI app with GET /health that returns status ok, a PostgreSQL ping, a Redis ping,
   and the current block number from CHAIN_RPC_URL using web3.py. Use pydantic-settings for config.
   Set up Alembic with an empty first migration. Add pytest, ruff and mypy configs.
3. docker-compose.yml with postgres and redis services.
4. frontend/: Next.js App Router + TypeScript + Tailwind + shadcn/ui init. One page that calls
   the backend /health and shows the block number and a connected wallet address using wagmi.
5. Makefile targets: dev (starts docker, hardhat node, deploys, backend, frontend), test
   (contracts, backend, frontend), lint, reset-db.
6. .env.example with DATABASE_URL, REDIS_URL, CHAIN_RPC_URL, CHAIN_ID, OPERATOR_PRIVATE_KEY,
   JWT_SECRET, INTERVAL_SECONDS, and contract address variables. .gitignore includes .env.
7. GitHub Actions workflow: contract tests, backend tests + ruff + mypy, frontend build, on every PR.
Then run everything and show me the smoke test results.
```

Acceptance checks:
- [ ] `make dev` starts the stack with no manual steps.
- [ ] GET /health returns ok with a block number.
- [ ] The frontend page shows the block number and the wallet address after connecting MetaMask (chain ID 31337).
- [ ] `make test` and CI are green.

---

## Phase 1: Pricing engine (SDR)

Goal: a pure, fully tested pricing module.

```text
Implement backend/app/engine/pricing.py and tests in backend/tests/engine/test_pricing.py.

Data types (dataclasses): Position(participant_id: str, side: 'buy'|'sell', qty_kwh: float,
limit_price: float, reputation: float) and PriceResult(sdr, p_raw, p_ref, supply, demand).
Function: compute_reference_price(positions, prev_p_ref, params) -> PriceResult.

Math (implement exactly):
 w_i = min(1, R_i / R_ref), R_ref = 0.8
 For each side, cap_q = c * median(q on that side), c = 3. Effective qty = min(q_i, cap_q).
 S = sum over sellers of w_j * effective_q_j ; D = sum over buyers of w_i * effective_q_i
 SDR = S / max(D, eps)
 p_raw = p_fit + (p_ret - p_fit) / (1 + SDR ** k), k = 2
 p_ref = clip(alpha * p_raw + (1 - alpha) * prev_p_ref, p_fit, p_ret), alpha = 0.7
 If prev_p_ref is None, p_ref = clip(p_raw, p_fit, p_ret).
 Zero demand -> p_ref = p_fit. Zero supply -> p_ref = p_ret. Empty market -> p_ref = midpoint.

Required unit tests (use params p_fit=3, p_ret=8, k=2, no smoothing):
 SDR 0.25 -> 7.71 ; 0.5 -> 7.00 ; 1 -> 5.50 ; 2 -> 4.00 ; 4 -> 3.29 (tolerance 0.01).
Hypothesis property tests:
 - p_ref is always within [p_fit, p_ret].
 - p_raw is non-increasing as supply grows (demand fixed).
 - Adding 50 new identities with reputation 0.1 and tiny quantities changes p_raw by less than 1%
   of (p_ret - p_fit).
 - One participant doubling its quantity moves p_raw less when the median cap is on than off.
Also add a function price_impact(positions, participant_id, delta_kwh, params) that returns the
change in p_raw if that participant adds delta_kwh; it will be used for the fairness metrics.
Run all tests and show the output.
```

Acceptance checks:
- [ ] All five worked values pass.
- [ ] Hypothesis tests pass with at least 200 examples each.
- [ ] mypy and ruff clean.

---

## Phase 2: Matching and clearing engine

Goal: the optimizer, grid constraints, EV handling, and a deterministic clearing pipeline.

```text
Implement in backend/app/engine/: grid.py, matching.py, clearing.py, hashing.py, plus tests.

grid.py: a radial feeder as a tree (nodes, lines with capacity_kw and from/to). Provide
path(node_a, node_b) returning the list of (line_id, direction +1/-1), and a helper that builds
the matrix pi[line][(buyer, seller)]. Include a default 13-node feeder fixture. The root node is
the transformer/grid; unmatched imports and exports flow through the root and must be counted
in line flows.

matching.py: solve with cvxpy (Clarabel or OSQP). x_ij >= 0 is the kWh seller j sells to buyer i.
 maximize  sum_ij [ (b_i - a_j) + beta * min(R_j, R_cap) ] * x_ij  -  lambda * sum_{k in long side} (y_k - s_k)^2
 where y_k = total matched to long-side participant k; s_k = (short_side_total * q_k / long_side_total);
 the long side is sellers if SDR > 1 else buyers.
 subject to:
  sum_i x_ij <= q_j for each seller ; sum_j x_ij <= q_i for each buyer
  x_ij = 0 unless a_j <= p_ref <= b_i, R_i >= rho_min, R_j >= rho_min, R_j >= r_min_i (buyer's min seller reputation, default 0)
  for each line l: | sum_ij pi[l][ij] * x_ij / dt + grid flows | <= capacity_l, dt = 0.25 h
 Pre-filter ineligible pairs before building the problem. All trades clear at the single price p_ref.
 Unmatched buy volume is bought from the grid at p_ret; unmatched supply is exported at p_fit.

EV support: an EV buyer's limit price b_i = p_fit + (p_ret - p_fit) * u_i with
 u_i = clip(E_need / (P_max * T_left), 0, 1). An EV with V2G may sell
 q_sell = max(0, SOC - E_target) only if v2g is True. Put this in a small ev.py.

clearing.py: clear_interval(positions, feeder, params, prev_p_ref) does: pricing -> matching ->
 convert to integers (Wh) with round-down then a largest-remainder repair pass that keeps every
 constraint satisfied -> returns trades, p_ref, unmatched amounts, line loadings.

hashing.py: canonical JSON (sorted keys, no spaces), keccak256, Merkle root over sorted revealed
 positions (input root), result hash over the trade list + p_ref. Same inputs must always give the
 same hashes.

Tests: no constraint violated; no participant exceeds quantity; all trades at p_ref; capacity zero
on a line means no trade crosses it; very large capacities equal the unconstrained solution;
proportional-share behaviour (two sellers with 3:1 offers and low demand get about 3:1 of it);
participants below rho_min get no peer trade; EV urgency raises the limit price; running clear_interval
twice gives identical hashes; a benchmark test printing the clearing time for 50, 100 and 200
participants (it should be well under a few seconds). Show all test output.
```

Acceptance checks:
- [ ] All constraint and determinism tests pass.
- [ ] 200 participants clear in a few seconds or less.
- [ ] Hash is identical across two runs and across two machines (run in Docker once).

---

## Phase 3: Reputation, defenses and fairness metrics

Goal: the research core, pure functions with tests.

```text
Implement in backend/app/reputation/: score.py, tiers.py, shortfall.py, sybil.py, fairness.py,
and tests in backend/tests/reputation/.

score.py: state per participant = (alpha, beta, evidence_count).
 Per-interval evidence: s_t = w_del*r_del + w_rev*r_rev + w_hon*r_hon + w_col*(1 - c_i)
  with weights (0.45, 0.15, 0.20, 0.20); r_del = min(1, delivered/promised), r_rev in {0,1},
  r_hon = 1 - anomaly score, c_i = collusion suspicion.
 Evidence weight n_t = min(1, v_t / v_ref) where v_t is traded kWh this interval.
 Update with forgetting: alpha_t = phi*alpha_{t-1} + n_t*s_t ; beta_t = phi*beta_{t-1} + kappa*n_t*(1 - s_t)
  where phi = 0.5 ** (1 / H), H = 672 intervals, kappa = 3. Prior (alpha0, beta0) = (1, 2).
 mu = alpha/(alpha+beta) ; sigma = sqrt(alpha*beta / ((alpha+beta)**2 * (alpha+beta+1)))
 R = max(0, mu - z*sigma), z = 1.
 Worked test values with phi = 1 and perfect full-volume intervals (s_t = 1, n_t = 1):
  0 intervals -> 0.098 ; 1 -> 0.276 ; 2 -> 0.400 ; 5 -> 0.606 ; 20 -> 0.856 ; 50 -> 0.936 (tol 0.002).
 Extra tests: a failure is penalized about 3x more than a success is rewarded; with phi < 1 old
 evidence fades (a participant that stops delivering loses Trusted tier over time; a participant that
 failed long ago recovers); zero-volume intervals add no evidence.

tiers.py: Suspended (R < 0.15 or high-severity flag), Probation (R < 0.3 or evidence_count < 20),
 Standard (0.3 <= R < 0.8), Trusted (R >= 0.8 and evidence_count >= 100). Volume cap
 Q_max = Q_base * (0.2 + 0.8 * R).

shortfall.py: for shortfall e = promised - delivered: compensation to buyer = e * (p_ret - p_ref);
 penalty fee = f * e * p_ref with f = 0.1. Return integer paise amounts.

sybil.py:
 - collusion: from a trade list over a sliding window build V_ij (energy sold i to j).
   PC_i = max_j (V_ij + V_ji) / sum_k (V_ik + V_ki)
   RR_i = sum_j min(V_ij, V_ji) / sum_j V_ij
   c_i = clip(max((PC_i - 0.5) / 0.5, RR_i), 0, 1)
   Also run networkx community detection (Louvain) and report communities with an internal
   volume ratio above 0.8.
 - IsolationForest (scikit-learn, fixed random_state) over per-participant features: position-size
   variance, acceptance rate, volume share, limit-price offset. Output anomaly scores in 0 to 1.
 - false reports: plausibility check (reported PV output must not exceed rated_kw * clear_sky_factor * 1.1)
   and an energy balance check (sum of participant readings on a feeder versus a substation meter
   within a tolerance). Output a_i in 0 to 1.
 - Flags are data records (kind, severity, evidence JSON). They never ban anyone automatically.

fairness.py (all take lists of per-participant results): jain_index, gini, hhi, small_actor_parity,
 price_impact (uses pricing.price_impact), reputation_mobility, reputation_gini, welfare_efficiency.
 Definitions:
  Jain J = (sum f_k)^2 / (n * sum f_k^2), f_k = matched share of participant k's offer or demand
  Gini of per-participant welfare gain versus grid-only trading
  HHI = sum s_j^2, s_j = seller j share of matched volume
  small_actor_parity = (matched volume share of smallest 50% of participants) / (their offered volume share)
  welfare_efficiency = matched welfare / unconstrained optimal welfare
 Tests with hand-computed small examples (for example four equal participants give J = 1,
 one winner among four gives J = 0.25, Gini of equal values is 0).
Show all test output.
```

Acceptance checks:
- [ ] Reputation worked table passes.
- [ ] Collusion test: a 2-person wash-trading pair scores c_i close to 1; an ordinary diversified trader scores close to 0.
- [ ] Fairness tests match hand calculations.

---

## Phase 4: Simulator and baselines (headless)

Goal: run whole markets from the command line, with honest and malicious bots, and the four baselines.

```text
Implement backend/app/sim/ and a CLI: python -m app.sim.cli simulate --scenario <name>
--participants 100 --days 7 --seed 42 --defenses on|off --out results/<run>.
1. forecast.py / meters.py: per-participant 15-minute demand (daily curve with morning and evening
   peaks, household scale, noise), solar (clear-sky bell curve times a slowly varying cloud factor,
   scaled by rated kW), simple battery model (SOC, efficiency), EV arrivals with departure time and
   required SOC. Each participant has a key pair; meter readings are signed (secp256k1) and verified.
   Everything takes a seed.
2. bots.py: honest; lazy (delivers X% less than promised); strategic bidder; colluding ring (members
   trade only with each other at attractive prices); Sybil farm (many small new identities);
   price manipulator (fake demand or withheld supply); false reporter (inflates production by X%);
   build-trust-then-defect (behaves for N intervals, then under-delivers).
3. runner.py: for each interval, collect positions, run engine.clearing, apply meter data, compute
   deliveries, update reputation (Phase 3), run the detection windows every 12 intervals, compute
   fairness metrics. Writes CSVs: intervals, trades, reputation, flags, fairness, plus config.json
   and the git commit hash.
4. baselines.py: B0 grid only; B1 fixed mid-price with first-come matching, no reputation;
   B2 SDR pricing with proportional allocation, no reputation, no grid constraints;
   B3 the full system. A --mode flag selects which one runs.
5. scenarios.py: a registry with the scenarios above, each with parameters.
6. Tests: the same seed gives identical output; a 100-participant, 1-day honest run completes and
   B3 never violates a line capacity; the lazy bot ends with lower reputation than honest ones.
Show the commands you ran and a summary table of key metrics for B0 to B3 on an honest 1-day run.
```

Acceptance checks:
- [ ] A 7-day, 100-participant honest run finishes and produces all CSVs.
- [ ] Same seed gives identical CSVs.
- [ ] Buyer bills under B1, B2, B3 are lower than B0 (sanity check, not a claim).

---

## Phase 5: Smart contracts

Goal: four audited-by-test contracts and a deploy script.

```text
In contracts/, implement with Solidity (recent stable 0.8.x) and OpenZeppelin.
Units: energy uint64 in Wh, price uint32 in paise per kWh, scores uint16 basis points. MockINR has
2 decimals (1 unit = 1 paisa). Payment = qtyWh * pricePaise / 1000 rounded down.

1. MockINR.sol: ERC-20 with faucet() limited per address per day.
2. Registry.sol: stake(amount), register(bytes32 meterKeyHash) (one identity per meter key hash,
   minimum stake required), requestWithdraw(), withdraw() after a cooldown, slash(participant, amount,
   beneficiary) callable only by Settlement, suspend(participant) by operator. Events: Registered, Slashed.
3. Settlement.sol (AccessControl roles: OPERATOR; Pausable; ReentrancyGuard):
   - openInterval(id, commitDeadline, revealDeadline)
   - commitPosition(id, commitHash): one commit per participant per interval, only before the deadline.
     commitHash = keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt))
   - deposit(amount), withdrawEscrow(amount): internal escrow balances, no ERC-20 transfer per trade.
   - postClearing(id, inputRoot, resultHash, pRefPaise): operator only, only after reveal closes.
   - settleBatch(id, Trade[] trades): every trade must be at pRef, buyer must have enough escrow,
     each trade settles at most once; moves escrow from buyer to seller.
   - postDelivery(id, deliveryRoot) and settleShortfall(id, participant, shortfallWh, proof):
     Merkle-proved shortfall pays compensation and penalty from the seller's stake via Registry.slash.
   - Events: IntervalOpened, PositionCommitted, ClearingPosted, TradeSettled, DeliveryPosted, ShortfallSettled.
4. ReputationAnchor.sol: postRoot(id, root) by operator; verifyScore(id, participant, scoreBp,
   evidenceCount, proof) view. Leaf = keccak256(abi.encodePacked(participant, scoreBp, evidenceCount)).
5. Tests (Hardhat, TypeScript, Chai): every function, every revert reason, access control, and
   scenarios: a full 10-participant interval; a participant who never reveals; a seller who
   under-delivers and is slashed; a buyer with too little escrow; a replayed commit in another interval;
   double settlement attempt; withdrawal before cooldown. Coverage above 90 percent. Gas report.
6. scripts/deploy.ts: deploys in order (token, Registry, ReputationAnchor, Settlement), wires roles,
   and writes addresses and ABIs to contracts/deployments/<network>.json. Works on hardhat and sepolia.
7. Run Slither if available and fix high and medium findings. Add NatSpec to every public function.
Show test output, coverage and the gas report.
```

Acceptance checks:
- [ ] All tests pass, coverage above 90 percent.
- [ ] You have personally read Settlement.sol and can explain every function.
- [ ] Deploy script runs on the local node and writes the JSON.

---

## Phase 6: Backend foundation

Goal: database, authentication, participants, configuration, audit log.

```text
In backend/app/, implement:
1. db/models.py (SQLAlchemy 2) and Alembic migrations for: users, participants, ev_state,
   feeder_nodes, feeder_lines, intervals, positions, trades, meter_readings, deliveries,
   reputation_events, reputation_scores, fairness_metrics, flags, config, audit_log, transactions.
   Money as integers. Unique constraint: one position per participant per interval.
   Intervals have a state enum: OPEN, COMMIT, REVEAL, CLEARING, SETTLED, METERED.
2. Auth with Sign-In With Ethereum: POST /auth/nonce, POST /auth/verify returning a short-lived JWT.
   Nonce is single use. Roles: participant, operator, admin; a dependency that enforces roles.
3. Participants: GET /me, POST /participants, PATCH /participants/{id}, with Pydantic validation
   (type consumer|prosumer|ev, pv_capacity_kw, battery_kwh, feeder_node_id, EV fields).
4. Config: a config table seeded from core/params.py; GET /admin/config and PUT /admin/config with
   an audit_log entry on every change. The engine reads params from the config table.
5. Seed script (python -m app.db.seed): feeder topology from the Phase 2 fixture, 20 simulated
   participants with wallet addresses from Hardhat accounts, default config.
6. Rate limiting (slowapi), CORS, structured logging (structlog), request size limits.
7. OpenAPI available at /docs, and a script that generates the TypeScript client into
   frontend/src/api (openapi-typescript).
8. Tests with a test database: auth flow, role checks, validation errors, config audit entries.
Show test output.
```

Acceptance checks:
- [ ] Login with a signed message works from a script.
- [ ] Non-admin cannot call admin routes.
- [ ] `make reset-db` then seed gives a clean demo state.

---

## Phase 7: Market lifecycle (backend and chain together)

Goal: a full interval runs automatically: commit, reveal, price, match, post, settle, meter, reputation, anchor.

```text
Implement backend/app/chain/ and backend/app/workers/ and the market API.
1. chain/client.py: web3.py client loading ABIs and addresses from contracts/deployments/<network>.json;
   nonce manager; every write recorded in the transactions table (status, tx hash) and idempotent
   (a restart must not double-send); wait for N confirmations (N=1 local, 2 sepolia).
2. workers/clock.py: scheduler (APScheduler) advancing the interval state machine every
   INTERVAL_SECONDS. Each transition is a guarded DB update and idempotent:
   OPEN -> COMMIT -> REVEAL -> CLEARING -> SETTLED -> METERED.
3. API: GET /intervals/current, GET /intervals/{id}, GET /price-history, POST /positions (validates one
   net position, stores it privately, returns commit hash data for the wallet), POST /positions/{id}/reveal
   (verifies the hash against the on-chain commit), GET /positions/mine, GET /orderbook (anonymized
   aggregate only), GET /trades, GET /trades/{id}.
4. workers/clearing.py: after REVEAL closes, load revealed positions, call engine.clear_interval,
   store trades, compute input root and result hash, store engine version (git hash).
   Unrevealed commits create a reveal_miss event.
5. workers/poster.py: calls Settlement.postClearing then settleBatch (chunk batches), retries safely.
6. workers/meter.py: collects simulated signed meter readings for the interval, verifies signatures,
   computes deliveries and the delivery root, calls postDelivery, settles shortfalls on chain.
7. workers/reputation.py: computes evidence, updates Beta state per participant (Phase 3 code),
   writes reputation_scores, builds the Merkle tree, posts the root to ReputationAnchor.
   API: GET /reputation/{address}, /reputation/{address}/history, /reputation/{address}/proof.
8. workers/listener.py: indexes contract events into PostgreSQL and reconciles mismatches.
9. WebSocket /ws with Redis pub/sub; channels: interval, price, trades, reputation, flags, grid.
10. Bot driver: in demo mode, simulated bot participants submit positions automatically through the
    same API and chain calls so the market is live without humans.
11. Integration test (docker-compose test profile + local hardhat): run 3 consecutive intervals with 10
    bots, then assert: trades match the engine output, escrow balances are consistent, the on-chain
    result hash equals the stored hash, a lazy bot's reputation dropped and its stake was slashed,
    and the on-chain reputation root verifies a Merkle proof for a participant.
Show the integration test output.
```

Acceptance checks:
- [ ] `make dev` with demo mode shows intervals advancing every 30 to 60 seconds with live trades.
- [ ] Killing and restarting the backend mid-interval does not double-settle.
- [ ] Integration test passes.

---

## Phase 8: Frontend foundation, onboarding, dashboard, trade

Goal: a polished shell and the core user flow.

```text
In frontend/ implement:
1. Design system: semantic tokens as CSS variables (surface, border, text, accent, success, warning,
   danger) with light and dark themes; deep navy primary, teal accent; Inter for UI and a serif for page
   titles; tabular numerals for prices and quantities; 8px spacing scale; consistent card style. Layout
   with a left sidebar on desktop and a bottom tab bar on mobile. Respect prefers-reduced-motion.
2. Plumbing: wagmi + viem wallet connection and network switching; TanStack Query; the generated API
   client; a WebSocket hook with reconnect and backoff that patches or invalidates query keys; a shared
   TxStatus flow (awaiting signature, pending, confirmed, failed with a readable reason); loading
   skeletons, empty states and error states with retry for every data view.
3. Pages:
   - Landing: one-paragraph explanation, live ticker (price, SDR, active participants), animated
     walk-through of one interval.
   - Onboarding wizard: connect wallet, Sign-In With Ethereum, choose participant type and enter
     equipment (PV, battery, EV), faucet tokens, stake and register on chain. React Hook Form + Zod.
   - Dashboard: current interval with CountdownRing, balance and escrow, reputation gauge and tier,
     last trades, grid status.
   - Trade: position form (buy or sell, kWh, limit price, optional deadline) with an expected price
     range and the grid-only comparison; a commit and reveal stepper that generates the salt, sends the
     commit transaction, then reveals; escrow deposit prompt if the balance is too low.
4. Accessibility: WCAG AA contrast, visible focus rings, keyboard navigable trade flow, aria-live for
   price updates, never colour alone for state. Units always labelled (kWh, kW, INR per kWh).
5. Tests: Vitest + Testing Library for components; one Playwright end-to-end test: connect, onboard,
   submit a position, see the trade appear.
Show screenshots or describe each page, and the test output.
```

Acceptance checks:
- [ ] A human can onboard and trade in the browser against the running stack.
- [ ] Works at 375, 768 and 1440 pixel widths.
- [ ] Playwright test green.

---

## Phase 9: Frontend market views

Goal: make the market and the reputation system legible.

```text
Add these pages to frontend/ using the existing design system and live data:
1. Market: PriceBandChart (live price against the feed-in and retail band), SdrGauge, anonymized
   DepthChart from /orderbook, TradesFeed, and an explanation tooltip on how the price was formed.
2. Grid map: a feeder tree (React Flow or D3) with line loading colours, highlighted congested lines,
   click a node to see its participants (pseudonymous).
3. Reputation: score history chart, ComponentRadar (delivery, reveal, honesty, collusion), TierLadder
   with the rules, a what-if panel ("how many perfect intervals to reach Trusted"), and a ProofVerifier
   button that fetches the Merkle proof and verifies it against ReputationAnchor on chain.
4. Fairness lab: MetricCards for Jain, Gini, HHI, small-actor parity, price impact, welfare efficiency;
   time-series charts; a toggle comparing baselines B2 and B3 when simulation results exist.
5. Polish: smooth number transitions on price ticks, tier-change celebration kept subtle, empty states
   with guidance, consistent chart styling and tooltips with units.
6. Tests for the new components and one Playwright test that visits each page without errors.
```

Acceptance checks:
- [ ] Every page updates live with no manual refresh.
- [ ] Proof verification shows success for a real participant.
- [ ] No console errors on any page.

---

## Phase 10: Attack lab, audit, admin, detection

Goal: the pages and jobs that demonstrate trust and fairness.

```text
Implement across backend and frontend:
1. Detection job (workers/detection.py): every 12 intervals run the Phase 3 collusion, Sybil and
   anomaly detectors over the sliding window, write flags, feed c_i and a_i into the reputation
   evidence. Admin flag queue: GET /admin/flags, POST /admin/flags/{id}/resolve. Flags never auto-ban.
2. Attack lab backend: POST /admin/attacks/run {scenario, params, defenses: on|off} runs the Phase 4
   scenario runner on an isolated simulated market (not the live one), stores results, and returns
   time series for price, attacker profit, reputation and fairness metrics. Scenarios: sybil_farm,
   collusion_ring, price_manipulation, false_reports, defect_after_trust.
3. Attack lab frontend: ScenarioPicker, parameter sliders, side-by-side charts with defenses off and on,
   an attacker profit meter, and a plain-language summary of what happened and which defense stopped it.
4. Audit: GET /audit/{interval_id} returns the published inputs (revealed positions), the result and the
   on-chain hashes; POST /audit/{interval_id}/rerun re-runs the engine at the stored engine version and
   returns recomputed hashes. Frontend Audit page: pick an interval, HashCompare view (stored, recomputed,
   on chain, all with match indicators), Merkle viewer for the input root, links to the block explorer.
5. Admin console: role-gated pages for parameters (with validation and a diff before saving), flag
   queue, simulation start/stop and speed, audit log table.
6. Tests: backend tests for audit re-run equality and for each scenario returning the expected shape;
   Playwright test for running an attack and opening the audit page.
```

Acceptance checks:
- [ ] Audit re-run reports matching hashes for a past interval.
- [ ] Running the Sybil scenario with defenses off shows attacker gain; with defenses on it collapses.
- [ ] Non-admin users cannot reach admin pages or routes.

---

## Phase 11: Experiments

Goal: the numbers and figures for your report. This is your research contribution.

```text
Using the Phase 4 CLI, implement experiments E1 to E10 as scripts under experiments/ that read a
config and a seed list, run at least 30 seeds, 7 simulated days (672 intervals), with 50, 100 and 200
participants, and save CSVs plus config and git commit hash.
 E1 honest: B0 to B3; buyer bill reduction, seller revenue uplift, welfare, Jain index.
 E2 Sybil farm: attacker adds 0, 10, 50 identities; price impact, attacker profit, attack cost.
 E3 collusion ring (5 to 10 members): time to reach Trusted with detection on and off; detection
    rate and false positives.
 E4 price manipulation: one seller withholds 0 to 50 percent of supply; price uplift and seller gain,
    with and without caps and reputation weighting.
 E5 false reports: inflation of 10 to 100 percent; detection rate against false positive rate (ROC).
 E6 defect after trust: intervals until reputation falls below the floor; loss to counterparties.
 E7 permanent elite: forgetting on and off, new entrants; reputation mobility, reputation Gini over
    time, time for a new entrant to reach Trusted.
 E8 grid limits: tighten line capacities in steps; constraint violations (must be zero), welfare
    efficiency, curtailed trades.
 E9 scalability: 50, 100, 200, 500 participants; clearing time and gas used per interval on the local
    chain, cost per trade.
 E10 ablations: remove, one at a time, the median cap, the lower confidence bound, forgetting, the
    fairness term, the collusion detector; report change in every metric.
Then write Jupyter notebooks that read only the saved CSVs and produce one figure per experiment
(matplotlib or seaborn, labelled axes with units, mean with confidence interval). Add
docs/RESULTS.md with a table mapping each figure to the exact command that produced it, and a short
honest limitations section (simulated meters, DC-style grid model, trusted operator).
```

Acceptance checks:
- [ ] Every figure regenerates with one command.
- [ ] You can explain why each result came out the way it did (if not, investigate before writing the report).
- [ ] Results are described as simulation findings under stated assumptions.

---

## Phase 12: Hardening, deployment and documentation

Goal: safe, reproducible, demo-ready.

```text
1. Security pass: run Slither on contracts and fix high and medium findings; npm audit and pip-audit;
   add a secret scanner to CI; confirm no private keys in the repo history; review CORS, rate limits and
   role checks on every route; confirm the frontend never holds a private key.
2. Deploy contracts to Sepolia with scripts/deploy.ts, verify them on Etherscan, and save addresses in
   contracts/deployments/sepolia.json. Keep the local node as the default for demos.
3. Deployment: Dockerfiles for backend and frontend; instructions in docs/DEPLOY.md for hosting the
   frontend (Vercel) and the backend plus PostgreSQL and Redis (one VM or Render/Railway) with
   environment variables listed.
4. Demo mode: a one-click "demo" command that resets the database, seeds 20 to 50 participants, starts
   bots with a 30 to 60 second interval and opens the app. Add a pre-funded demo wallet account.
5. Documentation: update this README with a screenshot of each page, the architecture diagram,
   quick start, and links to docs/. Add docs/ARCHITECTURE.md (layers, interval flow), docs/MATH.md
   (every formula and parameter), docs/CONTRACTS.md (generated from NatSpec), docs/DECISIONS.md.
6. Demo script in docs/DEMO.md (10 minutes): landing and live price; onboard a prosumer; submit a
   position and watch commit, reveal, clearing and settlement with the explorer link; market and grid map;
   reputation and proof verification; attack lab with defenses off then on; audit re-run; results table
   and limitations.
7. Final checks: fresh clone, follow the README quick start only, and confirm everything works.
```

Acceptance checks:
- [ ] A fresh clone runs with the README quick start alone.
- [ ] `make test` is green in CI.
- [ ] You can run the whole demo script without touching the terminal.

---

## Repair and review prompts (use when a phase goes wrong)

Failing tests:
```text
The tests for Phase N are failing (output below). Do not rewrite the tests to make them pass. Find the
root cause in the implementation, fix it, rerun, and explain the cause in two sentences. [paste output]
```

Agent went off-spec:
```text
You deviated from the spec in these places: [list]. Re-read the Phase N section of README.md and the
instruction file. Bring the code back in line with the spec without changing anything outside Phase N.
```

Review before committing:
```text
Review everything changed in this phase as a strict reviewer. List bugs, spec deviations, missing tests,
and security problems, ordered by severity. Do not fix anything yet; just report.
```

Explain it to me (use before your viva):
```text
Explain the code you wrote in this phase as if teaching a student: the purpose of each file, the data
flow, the formulas used, and the three most likely places for bugs. Keep it under 500 words.
```

Context reset (new session or after a limit):
```text
Read README.md, the instruction file and docs/DECISIONS.md. Run the test suites and tell me which phase
is complete. Continue with the next unfinished phase and nothing else.
```

---

## If time runs short, cut in this order

1. Paillier encryption and the on-chain challenge window (never planned in the phases above).
2. Locational congestion price adder.
3. Sepolia deployment (stay on the local node and say so).
4. V2G selling for EVs.
5. The interactive grid map (use a static diagram).

Never cut the reputation math, the fairness metrics or the attack experiments. They are the research contribution.

## Known limitations to state in the report

Simulated meters and a simulated grid, a DC-style flow approximation without voltage or losses, a
single operator who is trusted but verifiable (commitments, published inputs, deterministic re-run),
pseudonymous addresses that can still leak household behaviour, and parameters that are tuned in
simulation rather than measured on a real grid.