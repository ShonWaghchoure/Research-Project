"""Run every Phase 11 experiment (defaults to --smoke for safety)."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENTS = [
    "e1_honest",
    "e2_sybil",
    "e3_collusion",
    "e4_price_manipulation",
    "e5_false_reports",
    "e6_defect",
    "e7_permanent_elite",
    "e8_grid_limits",
    "e9_scalability",
    "e10_ablations",
]


def _load(name: str):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Phase 11 experiments")
    ap.add_argument(
        "--paper",
        action="store_true",
        help="Full paper matrix (30 seeds × 7 days × sizes). Very long.",
    )
    ap.add_argument("--only", nargs="*", default=None, help="Subset of experiment ids")
    ap.add_argument("--keep-raw", action="store_true")
    args = ap.parse_args(argv)

    selected = args.only or EXPERIMENTS
    smoke_flags = [] if args.paper else ["--smoke"]
    if args.keep_raw:
        smoke_flags.append("--keep-raw")

    # Ensure common is importable as sibling.
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))

    for name in selected:
        if name not in EXPERIMENTS:
            print(f"unknown experiment {name!r}; choose from {EXPERIMENTS}")
            return 2
        mod = _load(name)
        rc = mod.main_for(name, mod.build_variants, smoke_flags)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
