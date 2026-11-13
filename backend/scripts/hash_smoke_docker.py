"""Hash-only Docker smoke: compare input_root/result_hash to known local values.

Does not import cvxpy; uses fixed cleared trades from a local clear_interval run.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.hashing import input_root, result_hash
from app.engine.pricing import Position

EXP_IR = "0x484c8e421543daffcd361a28d35e507a746cc16cb66e69f76dd1d625775e7f85"
EXP_RH = "0x0939f7b109e20ef05213ee5401b9cabf89317f790e13469b89bf04826e95bb0d"
P_REF = 5.262443438914027


@dataclass(frozen=True)
class ClearedTrade:
    buyer_id: str
    seller_id: str
    qty_wh: int
    price: float


def main() -> None:
    positions = [
        Position("b0", "buy", 3.0, 8.0, 0.8, node_id="n4"),
        Position("b1", "buy", 2.0, 7.0, 0.8, node_id="n5"),
        Position("s0", "sell", 4.0, 3.0, 0.8, node_id="n8"),
        Position("s1", "sell", 1.5, 4.0, 0.8, node_id="n11"),
    ]
    trades = [
        ClearedTrade("b0", "s0", 2419, P_REF),
        ClearedTrade("b0", "s1", 581, P_REF),
        ClearedTrade("b1", "s0", 1468, P_REF),
        ClearedTrade("b1", "s1", 532, P_REF),
    ]
    ir = input_root(positions)
    rh = result_hash(trades, P_REF)
    print(ir)
    print(rh)
    print("match_local_expected", ir == EXP_IR and rh == EXP_RH)


if __name__ == "__main__":
    main()
