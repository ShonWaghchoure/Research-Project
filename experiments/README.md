# Phase 11 experiments

Research matrix for the report. Scripts wrap the Phase 4 simulator
(`app.sim.runner`) and never touch the live market API.

## Quick smoke (CI / local)

```bash
cd experiments
python run_all.py                 # all E1–E10 in smoke mode
python e1_honest.py --smoke       # one experiment
python figures/plot_all.py        # figures from results/phase11/*/metrics.csv
```

Smoke uses 1 seed, 20 participants, 1 day capped at 24 intervals, meters unsigned.

## Paper matrix

```bash
cd experiments
python run_all.py --paper
# or per experiment:
python e1_honest.py               # 30 seeds × 7 days × {50,100,200}
```

Full runs are long (hours). Outputs are under `results/phase11/` (gitignored).

## Layout

| Path | Role |
|------|------|
| `e1_honest.py` … `e10_ablations.py` | Experiment matrices |
| `common.py` | Shared harness → `metrics.csv` + `manifest.json` |
| `run_all.py` | Batch runner |
| `figures/plot_*.py` | Read-only figure generation |
| `notebooks/*.ipynb` | One notebook per experiment (CSV → figure) |
| `configs/` | Documented paper defaults |

Figure ↔ command map and limitations: [`docs/RESULTS.md`](../docs/RESULTS.md).
