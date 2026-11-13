"""Participant behaviours (honest and malicious) as small strategy objects.

A bot never touches the market directly. The runner calls these hooks:

    shape_position  adjust (side, qty, limit) before submission, or return None to abstain
    reveals         whether the committed position is revealed
    deliver         physical Wh actually delivered, given what was promised and what is available
    report_pv       PV generation written to the signed meter reading
    report_delivery delivered Wh written to the signed meter reading
    bilateral       pre-arranged wash trades (colluding ring only)

All randomness comes from the participant's own seeded generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

import numpy as np

Side = Literal["buy", "sell"]
Shaped = Optional[Tuple[Side, float, float]]


@dataclass
class Bot:
    kind: str = "honest"
    group: str = ""  # attacker group (sybil farm, ring) for profit accounting

    def shape_position(self, t: int, side: Side, qty_kwh: float, limit: float, p_fit: float, p_ret: float) -> Shaped:
        return (side, qty_kwh, limit)

    def reveals(self, t: int, rng: np.random.Generator) -> bool:
        return True

    def deliver(self, t: int, promised_wh: int, available_wh: int) -> int:
        return min(promised_wh, available_wh)

    def report_pv(self, t: int, actual_pv_kwh: float) -> float:
        return actual_pv_kwh

    def forecast_pv_multiplier(self, t: int) -> float:
        return 1.0

    def report_delivery(self, t: int, delivered_wh: int, promised_wh: int) -> int:
        return delivered_wh

    def bilateral(self, t: int, members: List[str], me: str) -> List[Tuple[str, str, float]]:
        return []

    @property
    def fake_demand(self) -> bool:
        return False

    @property
    def public_market(self) -> bool:
        return True


@dataclass
class Honest(Bot):
    kind: str = "honest"


@dataclass
class Lazy(Bot):
    """Delivers ``shortfall`` (e.g. 40%) less than promised."""

    kind: str = "lazy"
    shortfall: float = 0.4

    def deliver(self, t: int, promised_wh: int, available_wh: int) -> int:
        return int(min(promised_wh, available_wh) * (1.0 - self.shortfall))


@dataclass
class Strategic(Bot):
    """Overstates supply to win a bigger proportional share, asks at the floor, bids at the
    ceiling, and delivers only what it physically has."""

    kind: str = "strategic"
    inflate: float = 0.5

    def shape_position(self, t: int, side: Side, qty_kwh: float, limit: float, p_fit: float, p_ret: float) -> Shaped:
        if side == "sell":
            return (side, qty_kwh * (1.0 + self.inflate), p_fit)
        return (side, qty_kwh, p_ret)


@dataclass
class RingMember(Bot):
    """Colluding ring: members only trade with each other through pre-arranged bilateral deals
    (alternating direction, so flows are reciprocal) and report every one as fully delivered."""

    kind: str = "ring"
    qty_kwh: float = 1.0

    def bilateral(self, t: int, members: List[str], me: str) -> List[Tuple[str, str, float]]:
        k = len(members)
        if k < 2:
            return []
        i = members.index(me)
        partner = members[(i + 1) % k] if t % 2 == 0 else members[(i - 1) % k]
        return [(me, partner, self.qty_kwh)]

    @property
    def public_market(self) -> bool:
        return False


@dataclass
class SybilIdentity(Bot):
    """One of many cheap new identities posting fake demand at the ceiling to push the price up
    for the farm's real seller. It has no real load."""

    kind: str = "sybil"
    qty_kwh: float = 0.4

    def shape_position(self, t: int, side: Side, qty_kwh: float, limit: float, p_fit: float, p_ret: float) -> Shaped:
        return ("buy", self.qty_kwh, p_ret)

    @property
    def fake_demand(self) -> bool:
        return True


@dataclass
class Manipulator(Bot):
    """Large seller that withholds ``withhold`` of its supply to raise the clearing price."""

    kind: str = "manipulator"
    withhold: float = 0.3

    def shape_position(self, t: int, side: Side, qty_kwh: float, limit: float, p_fit: float, p_ret: float) -> Shaped:
        if side == "sell":
            return (side, qty_kwh * (1.0 - self.withhold), limit)
        return (side, qty_kwh, limit)


@dataclass
class FalseReporter(Bot):
    """Inflates reported PV by ``inflate``, offers the inflated surplus, and reports every sale as
    fully delivered while physically delivering only what it has."""

    kind: str = "false_reporter"
    inflate: float = 0.5
    start: int = 0  # active only for intervals in [start, end)
    end: int = 10**9

    def _on(self, t: int) -> bool:
        return self.start <= t < self.end

    def forecast_pv_multiplier(self, t: int) -> float:
        return 1.0 + self.inflate if self._on(t) else 1.0

    def report_pv(self, t: int, actual_pv_kwh: float) -> float:
        return actual_pv_kwh * (1.0 + self.inflate) if self._on(t) else actual_pv_kwh

    def report_delivery(self, t: int, delivered_wh: int, promised_wh: int) -> int:
        return promised_wh if self._on(t) else delivered_wh


@dataclass
class Defector(Bot):
    """Behaves honestly for ``after`` intervals, then stops delivering entirely."""

    kind: str = "defector"
    after: int = 192

    def deliver(self, t: int, promised_wh: int, available_wh: int) -> int:
        if t < self.after:
            return min(promised_wh, available_wh)
        return 0


@dataclass
class NonRevealer(Bot):
    """Commits but reveals only with probability ``p_reveal`` (keeps an option to back out)."""

    kind: str = "non_revealer"
    p_reveal: float = 0.7

    def reveals(self, t: int, rng: np.random.Generator) -> bool:
        return bool(rng.random() < self.p_reveal)


BOT_KINDS = {
    cls.kind: cls  # type: ignore[attr-defined]
    for cls in (Honest, Lazy, Strategic, RingMember, SybilIdentity, Manipulator, FalseReporter, Defector, NonRevealer)
}
