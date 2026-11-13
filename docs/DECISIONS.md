# Architecture & Implementation Decisions

## Phase 0: Walking Skeleton

1. **Python Environment**:
   - Python 3.12 is used via `uv` toolchain to guarantee binary wheel compatibility across data science and web3 packages (numpy, pydantic, web3.py).
   - Database driver: `psycopg` (v3) binary with SQLAlchemy 2.0 compatible URL `postgresql+psycopg://...`. Fallback handling automatically normalizes `postgresql://` to `postgresql+psycopg://` if needed.

2. **Smart Contracts**:
   - Hardhat TypeScript environment with `@nomicfoundation/hardhat-toolbox` and `@openzeppelin/contracts`.
   - `Ping.sol` includes a `ping()` external function emitting a `Pong` event and returning `"pong"`.
   - Deployment script `scripts/deploy.ts` saves contract deployments to `contracts/deployments/<network>.json` with contract address, transaction hash, and ABI.

3. **Backend Health Check**:
   - `GET /health` runs pings against PostgreSQL (via SQLAlchemy `SELECT 1`), Redis (via `redis.ping()`), and queries the latest block number from `CHAIN_RPC_URL` using `web3.py`.
   - Uses `pydantic-settings` to load `.env` configuration.
   - Initial Alembic migration (`0001_initial.py`) is created as an empty baseline migration.

4. **Frontend Architecture**:
   - Next.js 14/15 App Router with TypeScript and Tailwind CSS.
   - Configured with Wagmi and Viem connecting to Hardhat local node (chainId 31337).
   - Dashboard page polls/fetches backend `/health`, displays health metrics (status, postgres ping, redis ping, block number), and connects wallet via Wagmi showing address and balance.

5. **Tooling & Orchestration**:
   - `Makefile` coordinates `dev`, `test`, `lint`, and `reset-db`.
   - `docker-compose.yml` provides containerized PostgreSQL 16 and Redis 7.

## Phase 1: Pricing Engine (SDR)

1. **Units in tests vs production**:
   - Production params use paise/kWh (`p_fit=300`, `p_ret=800`).
   - Phase 1 worked-example tests use the spec's simplified INR/kWh units (`p_fit=3`, `p_ret=8`) with `alpha=1` (no smoothing). The formula is unit-agnostic as long as a call is internally consistent.

2. **Median-cap Sybil resistance**:
   - Spec: `cap_q = c * median(q on that side)`. A naive median over every offer is poisonable by many tiny low-rep identities (they pull the median down and cap honest volume).
   - Decision: compute the median only over positions with `reputation >= rho_min`. Low-rep Sybil offers still enter the weighted supply/demand sum (with `w_i = min(1, R_i/R_ref)`), but cannot rewrite the quantity cap. If no position on a side meets `rho_min`, fall back to the full-side median.

3. **Monotonicity property**:
   - "p_raw non-increasing as supply grows" is checked with `apply_median_cap=False`, so the test isolates the SDR formula. Changing book composition under an active median cap can move the median and is not globally monotonic; that behaviour is covered by the dedicated median-cap tests.

4. **Empty / one-sided markets**:
   - Empty → `p_ref = (p_fit + p_ret) / 2`, `sdr = 1`, `p_raw = midpoint`.
   - Zero demand (supply > 0) → `p_ref = p_fit`.
   - Zero supply (demand > 0) → `p_ref = p_ret`.

5. **`price_impact`**:
   - Returns `p_raw(after) - p_raw(before)` when `delta_kwh` is added to one participant's quantity. Raises `ValueError` if `participant_id` is missing. Uses `prev_p_ref=None` so the metric reflects raw price only.

## Phase 2: Matching and Clearing Engine

1. **QP formulation (vectorized cvxpy)**:
   - Decision variables are a flat non-negative vector over pre-filtered eligible pairs only (not a dense buyer×seller matrix).
   - Eligibility: `a_j <= p_ref <= b_i`, both reputations `>= rho_min`, and `R_j >= r_min_i`.
   - Objective: surplus `(b_i - a_j) + beta * min(R_j, R_cap)` minus `match_lambda * ||y - s||^2` on the long side (sellers if `SDR > 1`, else buyers).
   - Solvers tried in order: Clarabel → OSQP → SCS.

2. **Grid flow model**:
   - Peer trade `x_ij` contributes `pi[line][(buyer, seller)] * x_ij` along the unique radial path seller → buyer.
   - Unmatched buy volume imports from the root (`root → buyer`); unmatched sell volume exports to the root (`seller → root`).
   - Line constraint: `|peer_flow + grid_residual| / dt <= capacity_kw` with `dt = 0.25 h`.
   - Consequence: zero capacity on the path from a node to the root makes any positive offer at that node infeasible (even grid-only residuals); the matcher then returns no peer trades.

3. **Default feeder**:
   - 13-node radial tree (`n0` root/transformer + 12 downstream buses, 12 lines). Fixture helper `default_13_node_feeder`.

4. **Integerization**:
   - Continuous kWh trades are floored to Wh, then a largest-remainder pass awards at most +1 Wh per trade while respecting per-participant quantity caps.
   - After awarding remainders, line loadings are rechecked; if any line exceeds capacity, remainders are stripped in reverse award order until feasible.

5. **Hashing**:
   - `canonical_json`: sorted keys, no spaces.
   - `input_root`: Merkle root (keccak256 pairwise, odd-duplicate) over sorted revealed position records.
   - `result_hash`: keccak256 of canonical JSON `{p_ref, trades[]}` with trades sorted by `(buyer_id, seller_id, qty_wh, price)`.

6. **EV helpers** (`ev.py`):
   - Buy limit `b_i = p_fit + (p_ret - p_fit) * u_i` with `u_i = clip(E_need / (P_max * T_left), 0, 1)`.
   - V2G sell qty `max(0, SOC - E_target)` only when `v2g=True`.

## Phase 3: Reputation, Defenses and Fairness

Sources consolidated: GEMINI.md Phase 3 spec, the project report (IIIT-A Research Methodology, 2026),
the team edge-case document, and the literature noted below. Where the spec is explicit it is
implemented exactly; the items below are the gaps and how they were filled.

1. **Model provenance**: `score.py` is the Beta Reputation System (Josang & Ismail, 2002) with a
   forgetting factor, an asymmetric failure weight (kappa = 3) and a lower confidence bound
   (R = mu - z*sigma). Worked table (phi = 1) matches the spec to 1e-3.

2. **Newcomer deadlock (cold start)**: under the prior (1, 2), a newcomer has R = 0.098. The spec's
   tiers would suspend them (R < 0.15) and the Phase 2 matching gate excludes R < rho_min = 0.3, so
   they could never trade, never earn evidence and never recover. The report (section 5.4) requires
   that the cold-start barrier "does not permanently disadvantage genuine new entrants". Decision:
   - **Uncertainty never suspends**: R < 0.15 only means Suspended when the Beta mean is also
     below the prior mean (net-negative evidence). Otherwise the participant is Probation. This
     covers newcomers (R = 0.098 at the prior) and anyone whose R fell only because idle forgetting
     widened sigma (edge case 10). A newcomer who fully defaults falls below the prior mean and is
     suspended. (The first version used a newcomer-only grace; the Phase 4 simulator showed that
     idle decay still suspended newcomers, so the rule was generalised.)
   - Probation may trade P2P under the volume cap Q_max = Q_base*(0.2 + 0.8R).
     `tiers.matching_reputation()` returns max(R, rho_min) for Probation and 0 for Suspended.
   - **Hand-off (Phases 4 and 7)**: when building `engine.pricing.Position`, set
     `reputation = matching_reputation(state, tier)` and cap `qty_kwh` at `volume_cap_kwh(...)`.
     The Phase 2 engine is unchanged. Note that the SDR weight then gives Probation volume
     w = 0.3/0.8 = 0.375, so it is still discounted in pricing.
   - Result: perfect behaviour reaches Standard after 20 intervals and Trusted after 100
     (the evidence gate dominates), and the participant is never excluded on the way.

3. **Tier order**: high-severity flag -> Suspended; then Suspended (R < 0.15, newcomer grace
   above); Probation (R < 0.3 or evidence < 20); Trusted (R >= 0.8 and evidence >= 100); else Standard.

4. **Hysteresis (edge case 12)**: a downgrade only happens if R falls `hysteresis` = 0.02 below the
   boundary (e.g. Standard -> Probation at R < 0.28). Upgrades use the nominal thresholds.
   Enabled by passing `prev_tier` to `classify()`.

5. **evidence_count**: the number of intervals that contributed evidence (n_t > 0). It does not decay.

6. **Reveal misses**: a missed reveal trades nothing (v_t = 0) and would add no evidence, which would
   make not revealing free. A miss is therefore counted at full weight with r_rev = 0 and r_del = 0.

7. **v_ref** = 1.0 kWh per interval (a typical household 15-minute trade). Smaller trades give
   proportionally weaker evidence.

8. **Forgetting direction (edge case 10)**: the spec multiplies alpha and beta by phi, so the decay
   goes toward zero. A long-idle participant keeps the same *mean* but its uncertainty grows, so R
   falls; it does not decay toward a neutral 0.5. A `decay_to_prior` option (alpha <- alpha0 +
   phi*(alpha - alpha0)) exists but is off by default to follow the spec.

9. **Prior**: kept at (1, 2) from GEMINI.md (the worked table depends on it). The report's
   prototype started at 50/100. For display on the report's scale use `score_display(R)` (R*100).
   On-chain leaves use `score_bp(R)` (basis points).

10. **Fraud vs honest shortfall (edge cases 11 and 16)**: no separate w_fail weight. An honest
    shortfall only lowers r_del (pro-rated: r_del = delivered/promised), while detected fraud also
    lowers r_hon and raises a high-severity flag (-> Suspended, pending admin review).

11. **Shortfall money**: amounts = Wh * paise/kWh / 1000, rounded down, the same rule as the
    contract payment. Settlement pays for delivered energy pro-rata; over-delivery is not paid as P2P.

12. **Collusion**: the PC/RR formula is the spec's, adapted from wash-trading detection in
    crypto/NFT markets (no established P2P-energy method exists). Participants with no trades
    score 0. Known false-positive risk: a participant with one counterparty in the window has
    PC = 1. This is measured in experiment E3 rather than hidden by a heuristic.
    - Louvain runs on an undirected graph weighted by V_ij + V_ji, with a fixed seed. A cycle ring
      (A->B->C->A) evades the pairwise score but is caught here.
    - Communities covering > 50% of participants are ignored (in a small market the whole market
      can be one community).
    - Collusion flag at c_i >= 0.5; high severity at >= 0.9.

13. **Anomaly score**: IsolationForest (200 trees, fixed random_state, n_jobs = 1). a_i =
    clip((s - 0.5)/0.5, 0, 1), where s is the Liu et al. (2008) score (~0.5 normal, -> 1 anomalous).
    Plain min-max scaling was rejected because it always assigns 1.0 to someone, even in an honest
    market. With fewer than 8 participants all scores are 0. The literature shows IsolationForest
    is weak against stealthy false-data injection (~43% detection in one study), so it stays a
    20%-weight signal and never bans anyone.

14. **False reports**: PV plausibility gives a_i = 0 below rated_kw * clear_sky * dt * 1.1, rising
    linearly to 1 at twice that ceiling. The feeder energy-balance check cannot attribute a gap to
    a single meter, so it raises a feeder-level `energy_imbalance` flag and does not change anyone's
    score. Combined honesty input: a_i = max(anomaly, false_report).

15. **Fairness metric definitions left open by the spec**:
    - `reputation_mobility` = 1 - Spearman rank correlation between two snapshots (0 = frozen elite,
      2 = fully reversed); a constant snapshot (launch day) gives 0.
    - `price_impact`: per participant, |delta p_raw| from doubling its own quantity, as a fraction of
      (p_ret - p_fit), computed with `engine.pricing.price_impact`.
    - `gini` clips negative values to 0. Welfare gain vs grid-only is non-negative for trades at a
      p_ref in [p_fit, p_ret].
    - `small_actor_parity`: the smallest floor(n/2) participants by offered volume.
    - Empty or degenerate inputs return the neutral value (Jain 1, Gini 0, parity 1, efficiency 1).

16. **Report metrics added** (report sections 4.3 and 4.4, Nazir et al. [1]): seller satisfaction
    index, buyer bill saving %, seller revenue uplift %, buyer/seller surplus split, matching rate
    (market resilience), grid trust density, and grid-backup frequency (edge case 14).

17. **Phase 2 issues found while building Phase 3**: the `matching.py` AttributeError, the missing
    `cvxpy` pin and the unused import in `test_grid.py` were fixed on `main` in the Phase 2
    hardening commit (ce6db72) and merged into this branch.

## Phase 4: Simulator and Baselines

Sources consolidated: GEMINI.md Phase 4 spec, the project report (Table 3.2 scenarios, cohorts,
operational metrics; Nazir et al. [1] proportional allocation and bill-saving comparison), the team
edge-case document (cases 1-22), the Phase 3 hand-off notes, and Phase 2/5 conventions.

1. **Time and units**: 96 intervals/day, dt = 0.25 h. Physical models work in kWh; every market
   boundary is integer Wh; money is paise. Positions are rounded to whole Wh before clearing.

2. **Physical models** (`sim/forecast.py`):
   - Household load: base + morning (07:30) and evening (20:00) Gaussian peaks, 4-10 kWh/day,
     lognormal noise (sigma 0.15) between forecast and actual.
   - PV: clear-sky bell 06:00-18:00 times a shared feeder cloud factor (daily AR level + intra-day
     AR(1)). Positions use a **persistence forecast** (previous interval's cloud); delivery uses the
     actual cloud. The gap creates honest weather shortfalls (edge case 16) with no bad actors.
   - Battery: self-consumption first (charge on surplus, discharge on deficit), 95% one-way efficiency.
   - EV: overnight sessions; buy limit from `engine.ev` urgency. V2G sales are capped so the SoC
     never drops below the reserve AND the target stays reachable by departure, projecting the
     trajectory every interval (edge cases 7, 8). V2G is only offered when the EV needs no charge.

3. **Honest limit prices are near-truthful**: a participant's real alternative is the grid, so any
   P2P price in [p_fit, p_ret] beats it. Honest sellers ask p_fit + U(0, 10%) of the corridor and
   buyers bid p_ret - U(0, 10%). Wider margins (tried: 5-35%) priced honest participants out
   whenever the SDR price moved toward a bound, which made B1 look better than B2/B3 for reasons
   unrelated to the mechanism.

4. **Signed meters**: each participant has a deterministic secp256k1 key derived from the seed and
   its id. Each interval's reading (export, import, reported PV) is signed over keccak256 of its
   canonical JSON and verified by address recovery. `coincurve` (C backend for eth_keys) is pinned:
   it cuts sign+verify from ~8 ms to ~0.1 ms, so a 7-day, 100-participant run spends ~7 s on it.

5. **Bots**: honest, lazy, strategic (overstates supply, asks at the floor), colluding ring, Sybil
   identity, price manipulator (withholds supply), false reporter (inflates PV, claims full
   delivery), defector (honest for N intervals, then delivers nothing), and non-revealer.

6. **Colluding ring = bilateral wash trades**: every trade goes through central clearing, so a
   ring cannot trade only with itself inside the market. The ring is modelled as members trading
   through pre-arranged bilateral deals (the bilateral channel described by Nazir et al.), alternating
   direction so the flows are reciprocal, all reported fully delivered. The trades are settled at
   p_ref, logged with `channel = bilateral`, and visible to collusion detection.

7. **Sybil farm**: one large seller plus 30 extra identities (on top of `--participants`) posting
   fake demand at the ceiling. They have no load, so energy they win is exported at p_fit. With
   defenses on they are probation newcomers (SDR weight 0.375, volume cap). Buyer reputation comes
   from paying, so Sybil identities do earn buyer reputation; this is reported, not hidden.

8. **Baselines**: B0 grid only; B1 fixed mid price (550) with seeded first-come greedy matching;
   B2 Phase 1 SDR price (reputation weights neutral) with Nazir-style proportional allocation of the
   long side; B3 `engine.clearing.clear_interval`. All return `ClearingResult`, and line loadings
   are computed for every mode.

9. **`--defenses off`** (B3 only): positions go to the engine with reputation = 1 (no weights, no
   gate), no volume caps, and c_i / a_i are not fed into reputation. Detection still runs and logs
   flags so detection rates can be measured. The median cap stays on (it lives in the Phase 2
   engine); a switch for it belongs to the E10 ablations in Phase 11.

10. **Settlement**: a seller's delivered Wh is split across its trades pro rata. Each trade settles
    with `shortfall.settle_shortfall` on the *reported* delivery (the meter is the oracle). Every
    participant's physical residual (actual need - P2P received + P2P delivered) settles with the
    grid at p_ret / p_fit. Gains are measured against the same participant settling grid-only.

11. **Flags do not suspend in the simulator**: the tier rule "Suspended if high-severity flag"
    conflicts with "flags never ban anyone automatically". Suspension on a flag needs an admin
    decision (Phase 10), so in the simulator flags only feed c_i and a_i.

12. **Detection cadence**: every 12 intervals over a 96-interval window. c_i and a_i persist until
    the next pass. a_i = max(IsolationForest score, worst PV-plausibility score in the window).
    The feeder energy balance compares claimed export with physically delivered export and raises
    a feeder-level flag (no attribution).

13. **Line violations, two metrics**: `line_violations` counts physical overloads, including those
    from base household load the market cannot control (an 8 kW feeder overloads even under B0).
    `p2p_line_violations` counts overloads that P2P trading created or worsened, relative to the
    same positions settled grid-only. The spec's "B3 never violates a line capacity" is
    `p2p_line_violations == 0`. It holds in every scenario, and B3 relieves the grid (fewer
    physical overloads than B0).

14. **Determinism**: one `SeedSequence` spawns independent streams for weather, assignment, B1
    arrival order and each participant. All outputs except `timing.csv` are byte-identical for a
    given seed and code version (verified on a 7-day, 100-participant run). `config.json` records
    the git commit and a dirty flag.

15. **Output size**: `reputation.csv` is written hourly (every 4th interval plus the last) to keep
    7-day runs small. Everything else is per interval.

16. **Findings worth carrying into Phase 11**:
    - The SDR price passes most of the surplus to buyers when supply is plentiful, so seller uplift
      is lower than under a fixed mid price (B1) while buyer savings are higher.
    - On day 1 every participant is a capped newcomer, so B3 volume is below its steady state; use
      multi-day runs for comparisons.
    - 50% PV inflation is only provable on sunny intervals, so false reporters can end with higher
      reputation than honest sellers who take real weather shortfalls. Detection lowers their
      reputation (0.81 off vs 0.69 on in a 50-participant, 3-day run) but does not stop it. E5
      should quantify this.
    - The collusion score flags some honest participants who had a single counterparty in the
      window (the known PC = 1 false positive); E3 should report this rate.

## Phase 5: Smart Contracts

1. **Units**:
   - Energy `uint64` Wh; price `uint32` paise/kWh; reputation `uint16` basis points.
   - MockINR has 2 decimals (1 token unit = 1 paisa).
   - Payment = `qtyWh * pricePaise / 1000` (floor).

2. **Deploy order**:
   - MockINR → Registry → ReputationAnchor → Settlement → (Ping retained for Phase 0).
   - `Registry.SETTLEMENT_ROLE` granted to Settlement after deploy.
   - Addresses + ABIs written to `contracts/deployments/<network>.json`.

3. **Settlement design**:
   - Commit-reveal: on-chain commit only; reveal is off-chain (backend Phase 7).
   - Internal escrow via `deposit` / `withdrawEscrow`; `settleBatch` moves escrow buyer→seller at `pRef` only.
   - Shortfall leaf = `keccak256(abi.encode(intervalId, participant, shortfallWh))`; slash total (compensation + 10% penalty) to Settlement, then transfer compensation to buyer.

4. **Registry withdrawals**:
   - `requestWithdraw()` (no amount) queues all stake above `minStake` (or all stake if unregistered), then `withdraw()` after cooldown.

5. **ReputationAnchor**:
   - Leaf = `keccak256(abi.encodePacked(participant, scoreBp, evidenceCount))`; OZ MerkleProof (commutative pair hashing).

---

## Phase 8: Frontend Foundation

1. **Phase 7 is not built yet (teammate in progress), so the frontend runs against a mock.**
   - `frontend/mock/server.mjs` implements the Phase 7 API from GEMINI.md: `/intervals/current`, `/intervals/{id}`,
     `/price-history`, `/orderbook`, `/positions`, `/positions/{id}/reveal`, `/positions/mine`, `/trades`,
     `/trades/{id}`, `/reputation/{address}`, plus `/grid/status` and the `/ws` channels
     (interval, price, trades, reputation, grid, flags). It also serves the Phase 6 auth and participant routes.
   - It acts as the operator on the local Hardhat chain: it calls `Settlement.openInterval` for every interval and
     checks each reveal against the on-chain commit. Wallet transactions (faucet, stake, register, deposit, commit)
     are real.
   - Assumed response shapes live in `frontend/src/lib/api/types.ts` (marked "Phase 7"). When the real backend lands:
     run `make gen-api`, reconcile that file, and point `NEXT_PUBLIC_API_URL` at the backend.
   - Assumed extras the real Phase 7 should provide or the UI should drop: `Interval.commit_deadline`,
     `reveal_deadline`, `prev_p_ref_paise`, `active_participants`; `Reputation.components`, `intervals_to_trusted`,
     `volume_cap_kwh`; `GET /grid/status`; `Trade.status`; `POST /positions/{id}/reveal` body `{tx_hash}`.

2. **Interval must be open on chain before the API reports COMMIT.** Found by the end-to-end test: the operator's
   `openInterval` transaction landed about 7 s after the interval started, so the on-chain commit window was 13 s while
   the API advertised 20 s, and a commit near the end reverted with "commit closed". The mock now stays in OPEN until
   `openInterval` is confirmed. **Phase 7's clock worker should do the same.**

3. **Commit safety margin.** The trade page refuses new commits in the last 5 s of the commit window
   (signature + mining time) and says why, instead of letting the transaction revert.

4. **Commit hash computed in the browser and cross-checked.** The salt is generated with `crypto.getRandomValues`.
   The page computes `keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt))`
   and refuses to commit if the server's hash differs. Unit tests pin the encoding to values computed independently
   with Python `eth_abi`.

5. **Demo wallets.** On the local chain only, three Hardhat accounts (#2–#4) are offered as demo wallets through
   wagmi's `mock` connector, so the app can be used without MetaMask. wagmi's mock connector forwards
   `eth_accounts` to the node, which returns all 20 unlocked accounts with the operator first; without a pin every
   demo wallet would sign and send as the operator. Each demo connector is pinned to its own address
   (`frontend/src/lib/wagmi.ts`). Disabled when `NEXT_PUBLIC_CHAIN_ID` is not 31337 or
   `NEXT_PUBLIC_DISABLE_DEMO_WALLET=true`.

6. **Meter key for `Registry.register`.** The UI registers `keccak256("meter:" + lowercase address)`. A real
   deployment would hash the meter's public key; the simulator's per-participant keys are not exposed to the browser.

7. **Design system.** Requested direction: minimal, muted, professional, nothing bright.
   - Semantic CSS variables (surface, border, text, primary, accent, success, warning, danger) with light and dark
     themes; dark follows the OS unless the user picks one.
   - Deep navy primary, one desaturated teal accent; status colours are muted and always paired with text or an icon.
   - Inter for UI, Source Serif 4 for page titles only, tabular numerals for all numbers.
   - 8 px spacing scale (Tailwind `spacing` overridden: `1` = 8 px). 1 px borders, no shadows, 4 px radius.
   - Every page: header → key-figure row → main panel → secondary panels.
   - Desktop: fixed left sidebar. Mobile: bottom tab bar with the four main destinations.
   - Motion: countdown ring, price tweening and the landing walk-through only; all disabled under
     `prefers-reduced-motion`.

8. **Session storage.** The JWT is kept in `sessionStorage` (cleared when the tab closes) rather than
   `localStorage`, and the session is ignored if it belongs to a different wallet from the connected one.

9. **Shell-free pages.** Landing and onboarding render without the sidebar and do not open the WebSocket.

10. **Phase 9 pages.** Market, Grid, Reputation and Fairness use the Phase 8 design system and live mock data
    (price/orderbook/trades/grid/reputation/fairness). The feeder map is a fixed-layout SVG (not React Flow/D3)
    so it stays light and keyboard-accessible. Fairness B2 vs B3 series are simulated in the mock until the
    experiment store exists. ProofVerifier calls `GET /reputation/{addr}/proof` then `ReputationAnchor.verifyScore`.

11. **`/status`.** Shon's Phase 6 health and login demo page is kept as a plain System status page
    (backend health, session, contract addresses) instead of being deleted.
