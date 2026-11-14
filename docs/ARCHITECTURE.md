# Architecture

Layers of the Fair and Trustworthy P2P energy market, and the interval lifecycle.

## Layers

```text
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 + wagmi 2)                             │
│  dashboard · trade · market · grid · reputation · fairness  │
│  attack · audit · admin · status                            │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST + WebSocket
┌───────────────────────────▼─────────────────────────────────┐
│  Backend (FastAPI)                                          │
│  API routes · JWT/SIWE auth · SlowAPI rate limits           │
│  Workers (APScheduler): clock → clearing → poster → meter   │
│                         → reputation → detection            │
└───────┬───────────────────┬───────────────────┬─────────────┘
        │                   │                   │
   PostgreSQL            Redis              Chain RPC
   (state)            (pubsub/WS)        (Hardhat / Sepolia)
        │                                       │
        │              ┌────────────────────────▼──────────┐
        │              │  Contracts                        │
        │              │  MockINR · Registry · Settlement  │
        │              │  ReputationAnchor · Ping          │
        │              └───────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────┐
│  Pure engines (no I/O)                                      │
│  pricing (SDR) · matching · clearing · hashing              │
│  reputation score/tiers/sybil/fairness · sim runner         │
└─────────────────────────────────────────────────────────────┘
```

Research experiments (`experiments/`) call the headless simulator only — they never touch the live API or chain.

## Interval flow (demo / live market)

Typical demo interval length: **30–60 seconds** (`INTERVAL_SECONDS`, default 45).

```text
1. OPEN (clock)
   - Create interval row; open Settlement interval on-chain (commit/reveal deadlines).

2. COMMIT
   - Humans / demo bots deposit escrow, submit position commit hashes.
   - Positions stored with commit hash; quantity/side hidden until reveal.

3. REVEAL
   - Participants reveal (qty, side, salt); non-reveals → reveal-miss reputation evidence.

4. CLEAR (clearing worker)
   - Load revealed positions + feeder + reputation weights.
   - compute_reference_price (SDR) → match_orders (grid-aware) → integerize → hashes.
   - Persist trades, input root, result hash, line loadings.

5. POST (poster)
   - postClearing on Settlement; settle trades; optional shortfall postings.
   - Idempotent via `transactions` table.

6. METER
   - Simulated / signed meter readings; delivery root; shortfall settlement.

7. REPUTATION
   - Update Beta scores; classify tiers; Merkle root → ReputationAnchor.

8. DETECTION (every 12 metered intervals)
   - Collusion / anomaly / false-report flags (advisory only).
```

## Trust model

- **Operator** is trusted to run matching but **verifiable**: published inputs, deterministic audit re-run, on-chain roots/hashes.
- **Participants** may be strategic (Sybil, collusion, withhold, false reports); defenses are reputation gates, median caps, detection, and ablations studied in Phase 11.
- Frontend never holds operator private keys; wallets sign via wagmi (MetaMask or Hardhat demo connectors).

## Related docs

- [`MATH.md`](MATH.md) — formulas and parameters  
- [`CONTRACTS.md`](CONTRACTS.md) — on-chain surface  
- [`DEPLOY.md`](DEPLOY.md) — hosting  
- [`DEMO.md`](DEMO.md) — 10-minute walkthrough  
- [`DECISIONS.md`](DECISIONS.md) — design log  
- [`RESULTS.md`](RESULTS.md) — experiment figure map  
