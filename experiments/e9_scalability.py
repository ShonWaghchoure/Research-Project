"""E9 scalability: 50/100/200/500 participants; clear_ms (and gas when chain available)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

SIZES = (50, 100, 200, 500)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    # Smoke uses scale participants; paper uses SIZES (override --participants to customise).
    sizes = scale["participants"] if scale.get("max_intervals") and scale["days"] <= 1 else (
        scale["participants"] if scale["participants"] != [50, 100, 200] else list(SIZES)
    )
    for n in sizes:
        for seed in scale["seeds"]:
            yield Variant(
                label=f"scale_n{n}_s{seed}",
                cfg=cfg(
                    scenario="honest",
                    seed=seed,
                    participants=n,
                    days=scale["days"],
                    max_intervals=scale["max_intervals"],
                    sign_meters=scale["sign_meters"],
                ),
                tags={"n": n, "family": "scalability"},
            )


if __name__ == "__main__":
    raise SystemExit(main_for("e9_scalability", build_variants))
