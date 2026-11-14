"""E5 false reports: inflation 10–100%; detection rate vs false-positive rate (ROC)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

INFLATIONS = (0.1, 0.25, 0.5, 0.75, 1.0)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    inflations = (0.5,) if scale.get("max_intervals") and scale["days"] <= 1 else INFLATIONS
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for inflate in inflations:
                for defenses in (False, True):
                    yield Variant(
                        label=f"false_n{n}_i{int(inflate*100)}_d{int(defenses)}_s{seed}",
                        cfg=cfg(
                            scenario="false_reports",
                            seed=seed,
                            participants=n,
                            days=scale["days"],
                            defenses=defenses,
                            max_intervals=scale["max_intervals"],
                            sign_meters=scale["sign_meters"],
                            bot_param_overrides={"inflate": inflate},
                        ),
                        tags={
                            "n": n,
                            "inflate": inflate,
                            "defenses": defenses,
                            "family": "false_reports",
                        },
                    )


if __name__ == "__main__":
    raise SystemExit(main_for("e5_false_reports", build_variants))
