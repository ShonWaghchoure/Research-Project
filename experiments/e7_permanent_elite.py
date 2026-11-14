"""E7 permanent elite: forgetting on/off; mobility, reputation Gini, time to Trusted."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for forgetting in (True, False):
                yield Variant(
                    label=f"elite_n{n}_forget{int(forgetting)}_s{seed}",
                    cfg=cfg(
                        scenario="honest",
                        seed=seed,
                        participants=n,
                        days=scale["days"],
                        max_intervals=scale["max_intervals"],
                        sign_meters=scale["sign_meters"],
                        apply_forgetting=forgetting,
                    ),
                    tags={"n": n, "forgetting": forgetting, "family": "elite"},
                )


if __name__ == "__main__":
    raise SystemExit(main_for("e7_permanent_elite", build_variants))
