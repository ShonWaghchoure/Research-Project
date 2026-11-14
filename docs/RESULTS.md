# Phase 11 results

Simulation findings under the assumptions in GEMINI.md and `docs/DECISIONS.md`.
Figures are regenerated from saved CSVs only — never by re-running the market
inside a notebook.

## Figure ↔ command map

| Figure | Experiment | Produce metrics | Produce figure |
|--------|------------|-----------------|----------------|
| `e1_bill_saving.png` / `e1_revenue_uplift.png` | E1 honest B0–B3 | `cd experiments && python e1_honest.py [--smoke]` | `python figures/plot_all.py e1_honest` |
| `e2_attacker_gain.png` | E2 Sybil farm | `python e2_sybil.py [--smoke]` | `python figures/plot_all.py e2_sybil` |
| `e3_detection.png` | E3 collusion ring | `python e3_collusion.py [--smoke]` | `python figures/plot_all.py e3_collusion` |
| `e4_seller_gain.png` | E4 price manipulation | `python e4_price_manipulation.py [--smoke]` | `python figures/plot_all.py e4_price_manipulation` |
| `e5_detection.png` | E5 false reports | `python e5_false_reports.py [--smoke]` | `python figures/plot_all.py e5_false_reports` |
| `e6_welfare.png` | E6 defect after trust | `python e6_defect.py [--smoke]` | `python figures/plot_all.py e6_defect` |
| `e7_rep_gini.png` | E7 permanent elite | `python e7_permanent_elite.py [--smoke]` | `python figures/plot_all.py e7_permanent_elite` |
| `e8_violations.png` | E8 grid limits | `python e8_grid_limits.py [--smoke]` | `python figures/plot_all.py e8_grid_limits` |
| `e9_clear_ms.png` | E9 scalability | `python e9_scalability.py [--smoke]` | `python figures/plot_all.py e9_scalability` |
| `e10_ablations.png` | E10 ablations | `python e10_ablations.py [--smoke]` | `python figures/plot_all.py e10_ablations` |

Batch:

```bash
cd experiments
python run_all.py --smoke          # or --paper for the full matrix
python figures/plot_all.py
```

Outputs:

- Metrics: `results/phase11/<experiment>/metrics.csv`
- Per-run dirs: `results/phase11/<experiment>/runs/…`
- Figures: `results/phase11/figures/*.png`
- Git commit recorded in each `manifest.json`

## Paper scale (GEMINI.md)

| Knob | Paper default | Smoke default |
|------|---------------|---------------|
| Seeds | 30 (`1000…1029`) | 1 (`7`) |
| Days | 7 (672 intervals) | 1, capped at 24 intervals |
| Participants | 50, 100, 200 (E9 also 500) | 20 |
| Meter signing | on | off (faster) |

## Limitations (honest)

1. **Simulated meters.** Delivery and PV are model-generated and signed with
   deterministic secp256k1 keys. Real AMI noise, clock skew, and theft are out of scope.
2. **DC-style radial feeder.** Line limits use a linearised 13-node model; reactive
   power, voltage bands, and meshed topology are not modelled.
3. **Trusted operator.** Commit–reveal, clearing, and anchoring assume an honest
   operator process; the threat model is strategic *participants*, not a malicious
   matching engine.
4. **Gas on E9.** Smoke/paper metrics report clearing wall-time (`timing.csv`).
   On-chain gas per interval needs a local Hardhat node and is optional follow-up.
5. **Detection false positives.** Pairwise collusion scores can flag honest agents
   with a single counterparty in the window (see Phase 4 decisions); E3 reports this.

Treat every number as a **simulation finding under these assumptions**, not a field trial.
