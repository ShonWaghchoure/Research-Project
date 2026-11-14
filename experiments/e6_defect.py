"""E6 defect after trust: intervals until R falls below floor; counterparty loss."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    # Defect after ~2 days (192) in paper; smoke uses after=8 so collapse is visible.
    after = 8 if scale.get("max_intervals") and scale["days"] <= 1 else 192
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            yield Variant(
                label=f"defect_n{n}_after{after}_s{seed}",
                cfg=cfg(
                    scenario="defect_after_trust",
                    seed=seed,
                    participants=n,
                    days=scale["days"],
                    max_intervals=scale["max_intervals"],
                    sign_meters=scale["sign_meters"],
                    bot_param_overrides={"after": after},
                ),
                tags={"n": n, "after": after, "family": "defect"},
            )


if __name__ == "__main__":
    raise SystemExit(main_for("e6_defect", build_variants))
