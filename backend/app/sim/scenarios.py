"""Scenario registry.

Three families, consolidated from the project documents:
  * GEMINI.md Phase 4 attack scenarios (honest + the seven malicious behaviours).
  * Project report Table 3.2 market conditions: S1 balanced, S2 high demand, S3 surplus,
    S4 volatility, S10 stress.
  * Edge-case document stress tests: EV rush hour, tight grid, isolated participant,
    narrow price corridor, long absence, one-off fraud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class BotSpec:
    kind: str
    count: int = 0  # absolute number, or
    fraction: float = 0.0  # share of eligible participants
    eligible: Tuple[str, ...] = ("consumer", "prosumer", "ev")
    params: Dict[str, Any] = field(default_factory=dict)
    group: str = ""
    pv_multiplier: float = 1.0  # make attacker a large producer (manipulator, sybil master)


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    mix: Tuple[float, float, float] = (0.40, 0.45, 0.15)  # consumer, prosumer, ev
    pv_scale: float = 1.0
    load_scale: float = 1.0
    battery_share: float = 0.3
    v2g_share: float = 0.5
    cloud_volatility: float = 0.08
    capacity_kw: float = 100.0
    line_overrides: Dict[str, float] = field(default_factory=dict)
    ev_depart_mean_h: float = 8.0
    ev_depart_sd_h: float = 0.5
    bots: Tuple[BotSpec, ...] = ()
    sybil_count: int = 0
    isolated_node: bool = False  # keep exactly one participant at n12
    absence: Tuple[float, int, int] = (0.0, 0, 0)  # (fraction, first idle day, first active day again)
    params_overrides: Dict[str, Any] = field(default_factory=dict)


_SCENARIOS: Dict[str, Scenario] = {}


def register(s: Scenario) -> Scenario:
    _SCENARIOS[s.name] = s
    return s


def get(name: str) -> Scenario:
    if name not in _SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; available: {', '.join(sorted(_SCENARIOS))}")
    return _SCENARIOS[name]


def names() -> list[str]:
    return sorted(_SCENARIOS)


# ─── GEMINI.md Phase 4: honest and attack scenarios ────────────────────────────

register(Scenario("honest", "All participants behave honestly."))
register(Scenario(
    "lazy", "10% of sellers under-deliver by 40%.",
    bots=(BotSpec("lazy", fraction=0.10, eligible=("prosumer",), params={"shortfall": 0.4}),),
))
register(Scenario(
    "strategic", "10% of participants overstate supply by 50% and bid at the price limits.",
    bots=(BotSpec("strategic", fraction=0.10, eligible=("prosumer",), params={"inflate": 0.5}),),
))
register(Scenario(
    "collusion_ring", "A ring of 6 members wash-trades among themselves to farm reputation.",
    bots=(BotSpec("ring", count=6, eligible=("consumer", "prosumer"), group="ring", params={"qty_kwh": 1.0}),),
))
register(Scenario(
    "sybil_farm", "One large seller plus 30 fake low-reputation identities posting demand at the ceiling.",
    bots=(BotSpec("honest", count=1, eligible=("prosumer",), group="sybil_farm", pv_multiplier=4.0),),
    sybil_count=30,
))
register(Scenario(
    "price_manipulation", "One large seller withholds 30% of its supply to raise the price.",
    bots=(BotSpec("manipulator", count=1, eligible=("prosumer",), group="manipulator",
                  pv_multiplier=6.0, params={"withhold": 0.3}),),
))
register(Scenario(
    "false_reports", "5% of prosumers inflate reported PV by 50% and claim full delivery.",
    bots=(BotSpec("false_reporter", fraction=0.05, eligible=("prosumer",), params={"inflate": 0.5}),),
))
register(Scenario(
    "defect_after_trust", "5% of prosumers behave for 2 days, then stop delivering.",
    bots=(BotSpec("defector", fraction=0.05, eligible=("prosumer",), params={"after": 192}),),
))
register(Scenario(
    "non_revealer", "5% of participants reveal only 70% of their commitments.",
    bots=(BotSpec("non_revealer", fraction=0.05, params={"p_reveal": 0.7}),),
))

# ─── Project report Table 3.2 market conditions ────────────────────────────────

register(Scenario("s1_balanced", "Supply roughly equals demand during the day.", pv_scale=1.0))
register(Scenario("s2_high_demand", "Demand exceeds supply (low PV, higher load).", pv_scale=0.4, load_scale=1.3))
register(Scenario("s3_surplus", "Supply exceeds demand (high PV).", pv_scale=2.5, mix=(0.30, 0.60, 0.10)))
register(Scenario("s4_volatility", "Rapidly changing cloud cover.", cloud_volatility=0.30))
register(Scenario("s10_stress", "Full order book: equal buyers and sellers, high volume.", mix=(0.45, 0.45, 0.10), pv_scale=1.8, load_scale=1.5))

# ─── Edge-case document stress tests ───────────────────────────────────────────

register(Scenario(
    "ev_rush_hour", "Edge case 5: 40% EVs with tightly clustered departures.",
    mix=(0.30, 0.30, 0.40), ev_depart_mean_h=7.5, ev_depart_sd_h=0.1,
))
register(Scenario("grid_tight", "Tight line capacities (8 kW) force curtailment.", capacity_kw=8.0))
register(Scenario(
    "isolated_node", "Edge cases 14/19: participants at n12 sit behind a 1 kW line.",
    isolated_node=True, line_overrides={"l_n10_n12": 1.0},
))
register(Scenario(
    "narrow_corridor", "Edge case 13: feed-in tariff close to retail (750 vs 800 paise).",
    params_overrides={"p_fit": 750, "p_ret": 800, "beta": 2.5},
))
register(Scenario(
    "long_absence", "Edge case 10: 20% of participants idle from day 2 to day 5.",
    absence=(0.2, 2, 5),
))
register(Scenario(
    "one_fraud", "Edge case 11: one prosumer inflates reports by 300% for a single day (day 3).",
    bots=(BotSpec("false_reporter", count=1, eligible=("prosumer",),
                  params={"inflate": 3.0, "start": 192, "end": 288}),),
))
