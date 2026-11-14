"""E1 honest: B0–B3 baselines — buyer bill saving, seller uplift, welfare, Jain."""

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
            for mode in ("B0", "B1", "B2", "B3"):
                yield Variant(
                    label=f"honest_n{n}_{mode}_s{seed}",
                    cfg=cfg(
                        scenario="honest",
                        seed=seed,
                        participants=n,
                        days=scale["days"],
                        mode=mode,
                        max_intervals=scale["max_intervals"],
                        sign_meters=scale["sign_meters"],
                    ),
                    tags={"n": n, "mode": mode, "family": "honest"},
                )


if __name__ == "__main__":
    raise SystemExit(main_for("e1_honest", build_variants))
