"""Phase 2 hash determinism smoke: print input_root and result_hash twice."""

from __future__ import annotations

from app.core.params import MarketParams
from app.engine.clearing import clear_interval
from app.engine.grid import default_13_node_feeder
from app.engine.pricing import Position

PARAMS = MarketParams(
    p_fit=3,
    p_ret=8,
    k=2,
    alpha=1.0,
    c=3,
    r_ref=0.8,
    rho_min=0.3,
    r_cap=0.9,
    beta=0.25,
    match_lambda=1.0,
    dt_hours=0.25,
)


def main() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        Position("b0", "buy", 3.0, 8.0, 0.8, node_id="n4"),
        Position("b1", "buy", 2.0, 7.0, 0.8, node_id="n5"),
        Position("s0", "sell", 4.0, 3.0, 0.8, node_id="n8"),
        Position("s1", "sell", 1.5, 4.0, 0.8, node_id="n11"),
    ]
    a = clear_interval(positions, feeder, PARAMS, None)
    b = clear_interval(positions, feeder, PARAMS, None)
    print(a.input_root)
    print(a.result_hash)
    print(b.input_root)
    print(b.result_hash)
    print("match", a.input_root == b.input_root and a.result_hash == b.result_hash)


if __name__ == "__main__":
    main()
