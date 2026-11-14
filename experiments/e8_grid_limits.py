"""E8 grid limits: tighten capacities; violations must be zero; welfare; curtailment."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

CAPACITIES_KW = (100.0, 40.0, 20.0, 12.0, 8.0)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    caps = (100.0, 8.0) if scale.get("max_intervals") and scale["days"] <= 1 else CAPACITIES_KW
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for cap in caps:
                yield Variant(
                    label=f"grid_n{n}_c{int(cap)}_s{seed}",
                    cfg=cfg(
                        scenario="honest",
                        seed=seed,
                        participants=n,
                        days=scale["days"],
                        max_intervals=scale["max_intervals"],
                        sign_meters=scale["sign_meters"],
                        scenario_overrides={"capacity_kw": cap},
                    ),
                    tags={"n": n, "capacity_kw": cap, "family": "grid"},
                )


if __name__ == "__main__":
    raise SystemExit(main_for("e8_grid_limits", build_variants))
