"""Physical models for the simulator: household load, solar PV, battery and EV (seeded).

Interval = 15 minutes, 96 slots per day, dt = 0.25 h. Energy is kWh inside this module; the
runner converts to integer Wh at the market boundary.

Forecast vs actual: positions are built from the *forecast* (persistence cloud forecast and
expected load); delivery uses the *actual* values. The gap creates honest shortfalls
(edge case 16) without any bot misbehaving.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

SLOTS_PER_DAY = 96
DT_H = 0.25


def hour_of(slot: int) -> float:
    return (slot % SLOTS_PER_DAY) * DT_H


# ─── Load ──────────────────────────────────────────────────────────────────────


def _load_shape_raw(h: float) -> float:
    base = 0.35
    morning = 0.6 * math.exp(-0.5 * ((h - 7.5) / 1.0) ** 2)
    evening = 1.0 * math.exp(-0.5 * ((h - 20.0) / 1.5) ** 2)
    return base + morning + evening


_SHAPE_SUM = sum(_load_shape_raw(hour_of(s)) for s in range(SLOTS_PER_DAY))


def load_shape(slot: int) -> float:
    """Fraction of daily household energy used in this slot (sums to 1 over a day)."""
    return _load_shape_raw(hour_of(slot)) / _SHAPE_SUM


# ─── Solar ─────────────────────────────────────────────────────────────────────


def clear_sky_factor(slot: int) -> float:
    """Clear-sky output per kW rated, 0..1 (bell curve between 06:00 and 18:00)."""
    h = hour_of(slot)
    if h <= 6.0 or h >= 18.0:
        return 0.0
    return math.sin(math.pi * (h - 6.0) / 12.0) ** 1.5


@dataclass(frozen=True)
class Weather:
    """Shared cloud factor for the feeder (one locality), one value per interval."""

    cloud: tuple[float, ...]

    @staticmethod
    def generate(intervals: int, rng: np.random.Generator, volatility: float = 0.08) -> "Weather":
        days = max(1, math.ceil(intervals / SLOTS_PER_DAY))
        daily = []
        level = float(rng.uniform(0.6, 0.95))
        for _ in range(days):  # slowly varying day-to-day cloudiness
            level = float(np.clip(0.7 * level + 0.3 * rng.uniform(0.4, 1.0), 0.2, 1.0))
            daily.append(level)
        cloud = []
        x = 0.0
        for t in range(intervals):
            x = 0.85 * x + float(rng.normal(0.0, volatility))  # intra-day AR(1)
            cloud.append(float(np.clip(daily[t // SLOTS_PER_DAY] + x, 0.05, 1.0)))
        return Weather(cloud=tuple(cloud))

    def actual(self, t: int) -> float:
        return self.cloud[t]

    def forecast(self, t: int) -> float:
        """Persistence forecast: the previous interval's cloud factor."""
        return self.cloud[t - 1] if t > 0 else self.cloud[0]


def pv_kwh(rated_kw: float, slot: int, cloud: float) -> float:
    return rated_kw * clear_sky_factor(slot) * cloud * DT_H


# ─── Battery ───────────────────────────────────────────────────────────────────


@dataclass
class Battery:
    capacity_kwh: float
    soc_kwh: float
    p_max_kw: float = 3.0
    efficiency: float = 0.95  # one-way

    def dispatch(self, net_kwh: float) -> float:
        """Self-consumption: absorb surplus (net < 0) or cover deficit (net > 0).

        Returns the residual net (positive = still needs to buy, negative = surplus to sell).
        Mutates the state of charge.
        """
        step = self.p_max_kw * DT_H
        if net_kwh < 0:  # surplus -> charge
            room = (self.capacity_kwh - self.soc_kwh) / self.efficiency
            charge = min(-net_kwh, step, max(0.0, room))
            self.soc_kwh += charge * self.efficiency
            return net_kwh + charge
        if net_kwh > 0:  # deficit -> discharge
            avail = self.soc_kwh * self.efficiency
            discharge = min(net_kwh, step, max(0.0, avail))
            self.soc_kwh -= discharge / self.efficiency
            return net_kwh - discharge
        return 0.0


# ─── Electric vehicle ──────────────────────────────────────────────────────────


@dataclass
class EV:
    capacity_kwh: float
    p_max_kw: float
    v2g: bool
    reserve_frac: float = 0.2
    target_frac: float = 0.8
    soc_kwh: float = 0.0
    arrival: int = -1  # absolute interval index of current session
    departure: int = -1
    sessions: list[tuple[int, int, float]] = field(default_factory=list)  # (arrive, depart, soc)

    @property
    def target_kwh(self) -> float:
        return self.capacity_kwh * self.target_frac

    @property
    def reserve_kwh(self) -> float:
        return self.capacity_kwh * self.reserve_frac

    def plugged(self, t: int) -> bool:
        return self.arrival <= t < self.departure

    def start_session_if_due(self, t: int) -> None:
        for arrive, depart, soc in self.sessions:
            if arrive == t:
                self.arrival, self.departure, self.soc_kwh = arrive, depart, soc
                return

    def hours_left(self, t: int) -> float:
        return max(0.0, (self.departure - t) * DT_H)

    def need_kwh(self) -> float:
        return max(0.0, self.target_kwh - self.soc_kwh)

    def charge_kwh(self, t: int) -> float:
        """Energy to buy this interval (bounded by charger power and remaining need)."""
        if not self.plugged(t):
            return 0.0
        return min(self.p_max_kw * DT_H, self.need_kwh())

    def v2g_sell_kwh(self, t: int) -> float:
        """Sellable energy that keeps the reserve AND keeps the target reachable by departure.

        Edge cases 7 and 8: the SoC trajectory is projected to departure on every interval, and
        a sale that breaches the reserve or the target is capped before it reaches the market.
        """
        if not (self.v2g and self.plugged(t)):
            return 0.0
        step = self.p_max_kw * DT_H
        above_reserve = self.soc_kwh - self.reserve_kwh
        # after selling s now, remaining charging time must still reach target
        recharge_capacity = self.p_max_kw * max(0.0, self.hours_left(t) - DT_H)
        slack = self.soc_kwh + recharge_capacity - self.target_kwh
        return max(0.0, min(step, above_reserve, slack))

    def apply(self, delta_kwh: float) -> None:
        self.soc_kwh = float(np.clip(self.soc_kwh + delta_kwh, 0.0, self.capacity_kwh))


def ev_sessions(
    intervals: int,
    rng: np.random.Generator,
    capacity_kwh: float,
    arrive_mean_h: float = 18.5,
    arrive_sd_h: float = 1.0,
    depart_mean_h: float = 8.0,
    depart_sd_h: float = 0.5,
) -> list[tuple[int, int, float]]:
    """Overnight charging sessions: arrive in the evening, leave the next morning."""
    out = []
    days = math.ceil(intervals / SLOTS_PER_DAY)
    for d in range(days):
        a_h = float(np.clip(rng.normal(arrive_mean_h, arrive_sd_h), 15.0, 23.5))
        dep_h = float(np.clip(rng.normal(depart_mean_h, depart_sd_h), 5.0, 11.0))
        arrive = d * SLOTS_PER_DAY + int(a_h / DT_H)
        depart = (d + 1) * SLOTS_PER_DAY + int(dep_h / DT_H)
        soc = capacity_kwh * float(rng.uniform(0.15, 0.5))
        if arrive < intervals:
            out.append((arrive, min(depart, intervals), soc))
    return out
