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
   - A newcomer (evidence_count < 20) whose R has not fallen below the prior's R is **Probation**,
     not Suspended. A newcomer who defaults drops below the prior R and loses this grace.
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
