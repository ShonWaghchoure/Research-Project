"""Command line entry point.

    python -m app.sim.cli simulate --scenario honest --participants 100 --days 7 --seed 42 \
        --defenses on --mode B3 --out results/honest_b3
    python -m app.sim.cli compare  --scenario honest --participants 100 --days 1 --seed 42 --out results/cmp
    python -m app.sim.cli scenarios
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from app.sim import scenarios
from app.sim.baselines import MODES
from app.sim.runner import SimConfig, run


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scenario", default="honest", choices=scenarios.names())
    p.add_argument("--participants", type=int, default=100)
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--defenses", choices=["on", "off"], default="on")
    p.add_argument("--out", required=True)
    p.add_argument("--no-sign", action="store_true", help="skip meter signing (faster)")


def _cfg(a: argparse.Namespace, mode: str) -> SimConfig:
    return SimConfig(
        scenario=a.scenario, participants=a.participants, days=a.days, seed=a.seed,
        defenses=a.defenses == "on", mode=mode, sign_meters=not a.no_sign,
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.sim.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="run one market")
    _common(s)
    s.add_argument("--mode", choices=MODES, default="B3")

    c = sub.add_parser("compare", help="run B0..B3 on the same scenario and seed")
    _common(c)

    sub.add_parser("scenarios", help="list scenarios")

    a = ap.parse_args(argv)
    if a.cmd == "scenarios":
        for name in scenarios.names():
            print(f"{name:20s} {scenarios.get(name).description}")
        return 0
    if a.cmd == "simulate":
        summary = run(_cfg(a, a.mode), a.out)
        print(json.dumps(summary["market"], indent=2))
        print(f"wrote {a.out}")
        return 0

    rows = []
    for mode in MODES:
        summ = run(_cfg(a, mode), Path(a.out) / mode)
        m = summ["market"]
        rows.append((mode, m["bill_saving_pct"], m["revenue_uplift_pct"], m["gain_paise"], summ["line_violations"]))
    print(f"{'mode':5s} {'buyer bill saving %':>20s} {'seller revenue uplift %':>24s} {'total gain (INR)':>17s} {'line violations':>16s}")
    for mode, bs, ru, g, v in rows:
        print(f"{mode:5s} {bs:20.2f} {ru:24.2f} {g / 100:17.2f} {v:16d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
