"""E4 price manipulation: withhold 0–50%; uplift and seller gain ± caps/rep weights."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for

WITHHOLDS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    withholds = (0.0, 0.3) if scale.get("max_intervals") and scale["days"] <= 1 else WITHHOLDS
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for w in withholds:
                for defenses in (False, True):
                    for median in ((True,) if not defenses else (True, False)):
                        yield Variant(
                            label=f"manip_n{n}_w{int(w*100)}_d{int(defenses)}_m{int(median)}_s{seed}",
                            cfg=cfg(
                                scenario="price_manipulation",
                                seed=seed,
                                participants=n,
                                days=scale["days"],
                                defenses=defenses,
                                max_intervals=scale["max_intervals"],
                                sign_meters=scale["sign_meters"],
                                bot_param_overrides={"withhold": w},
                                apply_median_cap=median,
                            ),
                            tags={
                                "n": n,
                                "withhold": w,
                                "defenses": defenses,
                                "median_cap": median,
                                "family": "manipulation",
                            },
                        )


if __name__ == "__main__":
    raise SystemExit(main_for("e4_price_manipulation", build_variants))
