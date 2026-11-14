"""E2 Sybil farm: attacker adds 0 / 10 / 50 identities; price impact, profit, cost."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

SYBIL_COUNTS = (0, 10, 50)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    counts = (0, 10) if scale.get("max_intervals") and scale["days"] <= 1 else SYBIL_COUNTS
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for sybils in counts:
                for defenses in (False, True):
                    yield Variant(
                        label=f"sybil_n{n}_k{sybils}_d{int(defenses)}_s{seed}",
                        cfg=cfg(
                            scenario="sybil_farm",
                            seed=seed,
                            participants=n,
                            days=scale["days"],
                            defenses=defenses,
                            max_intervals=scale["max_intervals"],
                            sign_meters=scale["sign_meters"],
                            scenario_overrides={"sybil_count": sybils},
                        ),
                        tags={
                            "n": n,
                            "sybil_count": sybils,
                            "defenses": defenses,
                            "family": "sybil",
                        },
                    )


if __name__ == "__main__":
    raise SystemExit(main_for("e2_sybil", build_variants))
