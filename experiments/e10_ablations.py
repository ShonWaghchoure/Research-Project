"""E10 ablations: remove one defense at a time; report change in every metric."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

ABLATIONS = (
    ("full", {}),
    ("no_median_cap", {"apply_median_cap": False}),
    ("no_lcb", {"apply_lcb": False}),
    ("no_forgetting", {"apply_forgetting": False}),
    ("no_fairness_term", {"apply_fairness_term": False}),
    ("no_collusion_detector", {"apply_collusion_detector": False}),
)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    # Ablations on honest + one attack (sybil) so effect sizes are visible.
    scenarios = ("honest", "sybil_farm")
    if scale.get("max_intervals") and scale["days"] <= 1:
        scenarios = ("sybil_farm",)
        ablations = ABLATIONS[:3]  # full + two ablations in smoke
    else:
        ablations = ABLATIONS
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for scenario in scenarios:
                for name, kwargs in ablations:
                    yield Variant(
                        label=f"abl_{scenario}_n{n}_{name}_s{seed}",
                        cfg=cfg(
                            scenario=scenario,
                            seed=seed,
                            participants=n,
                            days=scale["days"],
                            max_intervals=scale["max_intervals"],
                            sign_meters=scale["sign_meters"],
                            **kwargs,
                        ),
                        tags={
                            "n": n,
                            "scenario": scenario,
                            "ablation": name,
                            "family": "ablation",
                        },
                    )


if __name__ == "__main__":
    raise SystemExit(main_for("e10_ablations", build_variants))
