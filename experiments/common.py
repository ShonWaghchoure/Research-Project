"""Shared Phase 11 experiment harness.

Each E1–E10 script builds a list of run variants, then calls ``run_matrix``.
Outputs land under ``results/phase11/<experiment>/`` (gitignored via ``results/``).

Usage (from repo root)::

    cd backend && ../.venv/bin/python ../experiments/e1_honest.py --smoke
    # or:
    cd backend && .venv/bin/python -c "import runpy; runpy.run_path('../experiments/e1_honest.py')"
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.sim.runner import SimConfig, git_commit, run  # noqa: E402

RESULTS_ROOT = ROOT / "results" / "phase11"
CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


@dataclass
class Variant:
    """One simulation cell in an experiment matrix."""

    label: str
    cfg: SimConfig
    tags: Dict[str, Any] = field(default_factory=dict)


def paper_seeds(n: int = 30, base: int = 1000) -> List[int]:
    return [base + i for i in range(n)]


def smoke_seeds() -> List[int]:
    return [7]


def load_config(name: str) -> Dict[str, Any]:
    path = CONFIGS_DIR / name
    if not path.exists():
        path = CONFIGS_DIR / f"{name}.json"
    return json.loads(path.read_text())


def mean_fairness(out: Path, key: str = "jain") -> Optional[float]:
    fair = out / "fairness.csv"
    if not fair.is_file():
        return None
    vals: List[float] = []
    with fair.open(newline="") as f:
        for row in csv.DictReader(f):
            raw = row.get(key) or row.get("gini_gain" if key == "gini" else key)
            if raw not in (None, ""):
                try:
                    vals.append(float(raw))
                except ValueError:
                    pass
    return sum(vals) / len(vals) if vals else None


def mean_clear_ms(out: Path) -> Optional[float]:
    timing = out / "timing.csv"
    if not timing.is_file():
        return None
    vals: List[float] = []
    with timing.open(newline="") as f:
        for row in csv.DictReader(f):
            raw = row.get("clear_ms")
            if raw not in (None, ""):
                try:
                    vals.append(float(raw))
                except ValueError:
                    pass
    return sum(vals) / len(vals) if vals else None


def flatten_summary(summary: Dict[str, Any], tags: Dict[str, Any], out: Path) -> Dict[str, Any]:
    market = summary.get("market") or {}
    row: Dict[str, Any] = {
        **tags,
        "scenario": summary.get("scenario"),
        "mode": summary.get("mode"),
        "defenses": summary.get("defenses"),
        "seed": summary.get("seed"),
        "participants": summary.get("participants"),
        "intervals": summary.get("intervals"),
        "bill_saving_pct": market.get("bill_saving_pct"),
        "revenue_uplift_pct": market.get("revenue_uplift_pct"),
        "gain_paise": market.get("gain_paise"),
        "line_violations": summary.get("line_violations"),
        "p2p_line_violations": summary.get("p2p_line_violations"),
        "reputation_mobility": summary.get("reputation_mobility"),
        "reputation_gini_end": summary.get("reputation_gini_end"),
        "mean_jain": mean_fairness(out, "jain"),
        "mean_gini": mean_fairness(out, "gini"),
        "mean_welfare_efficiency": mean_fairness(out, "welfare_efficiency"),
        "mean_clear_ms": mean_clear_ms(out),
        "out_dir": str(out),
    }
    groups = summary.get("groups") or {}
    for gname, gstats in groups.items():
        row[f"group_{gname}_gain_paise"] = gstats.get("gain_paise")
        row[f"group_{gname}_bill_saving_pct"] = gstats.get("bill_saving_pct")
        row[f"group_{gname}_revenue_uplift_pct"] = gstats.get("revenue_uplift_pct")
    flags = summary.get("flags") or {}
    for kind, count in flags.items():
        row[f"flag_{kind}"] = count
    return row


def run_matrix(
    experiment: str,
    variants: Sequence[Variant],
    *,
    keep_raw: bool = False,
) -> Path:
    """Run every variant; write ``metrics.csv`` + ``manifest.json`` under results/phase11/<id>/."""
    exp_dir = RESULTS_ROOT / experiment
    exp_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    git = git_commit()

    for i, variant in enumerate(variants):
        cell = exp_dir / "runs" / f"{i:04d}_{variant.label}"
        cell.mkdir(parents=True, exist_ok=True)
        summary = run(variant.cfg, cell)
        (cell / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        tags = {"experiment": experiment, "label": variant.label, **variant.tags}
        rows.append(flatten_summary(summary, tags, cell))
        if not keep_raw:
            # Keep summary + fairness + intervals + timing; drop bulky per-trade CSVs for matrix runs.
            for name in ("trades.csv", "reputation.csv", "participants.csv"):
                p = cell / name
                if p.exists():
                    p.unlink()

    metrics_path = exp_dir / "metrics.csv"
    if rows:
        keys: List[str] = []
        seen = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        with metrics_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for row in rows:
                w.writerow(row)

    manifest = {
        "experiment": experiment,
        "n_runs": len(variants),
        "git": git,
        "metrics": str(metrics_path.relative_to(ROOT)) if metrics_path.exists() else None,
        "variants": [
            {"label": v.label, "tags": v.tags, "cfg": asdict(v.cfg)} for v in variants
        ],
    }
    (exp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n")
    print(f"[{experiment}] wrote {metrics_path} ({len(rows)} rows)")
    return exp_dir


def add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="Tiny matrix (few seeds, short horizon) for CI / local checks",
    )
    ap.add_argument(
        "--keep-raw",
        action="store_true",
        help="Retain trades/reputation/participants CSVs (large)",
    )
    ap.add_argument(
        "--seeds",
        type=int,
        nargs="*",
        default=None,
        help="Override seed list (default: 30 paper seeds, or smoke seed)",
    )
    ap.add_argument(
        "--participants",
        type=int,
        nargs="*",
        default=None,
        help="Override participant sizes",
    )
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument(
        "--max-intervals",
        type=int,
        default=None,
        help="Cap intervals (smoke default 24)",
    )


def resolve_scale(args: argparse.Namespace) -> Dict[str, Any]:
    """Map CLI flags to seeds / sizes / days / max_intervals."""
    if args.smoke:
        return {
            "seeds": args.seeds or smoke_seeds(),
            "participants": args.participants or [20],
            "days": args.days if args.days is not None else 1,
            "max_intervals": args.max_intervals if args.max_intervals is not None else 24,
            "sign_meters": False,
        }
    return {
        "seeds": args.seeds or paper_seeds(30),
        "participants": args.participants or [50, 100, 200],
        "days": args.days if args.days is not None else 7,
        "max_intervals": args.max_intervals,
        "sign_meters": True,
    }


def cfg(
    *,
    scenario: str,
    seed: int,
    participants: int,
    days: int,
    mode: str = "B3",
    defenses: bool = True,
    max_intervals: Optional[int] = None,
    sign_meters: bool = True,
    scenario_overrides: Optional[Dict[str, Any]] = None,
    bot_param_overrides: Optional[Dict[str, Any]] = None,
    apply_median_cap: bool = True,
    apply_lcb: bool = True,
    apply_forgetting: bool = True,
    apply_fairness_term: bool = True,
    apply_collusion_detector: bool = True,
) -> SimConfig:
    return SimConfig(
        scenario=scenario,
        seed=seed,
        participants=participants,
        days=days,
        mode=mode,
        defenses=defenses,
        max_intervals=max_intervals,
        sign_meters=sign_meters,
        scenario_overrides=scenario_overrides or {},
        bot_param_overrides=bot_param_overrides or {},
        apply_median_cap=apply_median_cap,
        apply_lcb=apply_lcb,
        apply_forgetting=apply_forgetting,
        apply_fairness_term=apply_fairness_term,
        apply_collusion_detector=apply_collusion_detector,
    )


def main_for(
    experiment: str,
    build_variants: Any,
    argv: Optional[Sequence[str]] = None,
) -> int:
    ap = argparse.ArgumentParser(description=f"Phase 11 experiment {experiment}")
    add_common_args(ap)
    args = ap.parse_args(argv)
    scale = resolve_scale(args)
    variants = list(build_variants(scale))
    run_matrix(experiment, variants, keep_raw=args.keep_raw)
    return 0
