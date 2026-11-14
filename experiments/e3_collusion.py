"""E3 collusion ring: time to Trusted with detection on/off; detection rate & FP."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from common import Variant, cfg, main_for  # noqa: E402

from app.sim import scenarios as sc_mod  # noqa: E402
from app.sim.scenarios import get  # noqa: E402


def build_variants(scale: Dict[str, Any]) -> Iterable[Variant]:
    sizes = (6,) if scale.get("max_intervals") and scale["days"] <= 1 else (5, 6, 8, 10)
    base = get("collusion_ring")
    for n in scale["participants"]:
        for seed in scale["seeds"]:
            for ring in sizes:
                for detect in (False, True):
                    name = f"collusion_ring_r{ring}"
                    if name not in sc_mod._SCENARIOS:  # noqa: SLF001
                        bots = tuple(replace(b, count=ring, fraction=0.0) for b in base.bots)
                        sc_mod.register(replace(base, name=name, bots=bots))
                    yield Variant(
                        label=f"ring_n{n}_r{ring}_det{int(detect)}_s{seed}",
                        cfg=cfg(
                            scenario=name,
                            seed=seed,
                            participants=n,
                            days=scale["days"],
                            max_intervals=scale["max_intervals"],
                            sign_meters=scale["sign_meters"],
                            apply_collusion_detector=detect,
                        ),
                        tags={
                            "n": n,
                            "ring_size": ring,
                            "detection": detect,
                            "family": "collusion",
                        },
                    )


if __name__ == "__main__":
    raise SystemExit(main_for("e3_collusion", build_variants))
