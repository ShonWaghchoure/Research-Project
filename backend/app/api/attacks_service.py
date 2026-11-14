"""Run Phase 4 scenarios in isolation for the attack lab (not the live market)."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

from app.schemas.attacks import ATTACK_SCENARIOS
from app.sim.runner import SimConfig
from app.sim.runner import run as sim_run
from app.sim.scenarios import get as get_scenario

# Short defaults so the UI stays responsive; callers may override via params.
_DEFAULTS = {
    "participants": 40,
    "days": 1,
    "seed": 42,
}


def _plain_summary(scenario: str, defenses: bool, summary: dict[str, Any]) -> str:
    groups = summary.get("groups") or {}
    flags = summary.get("flags") or {}
    attacker_gain = 0.0
    for g, stats in groups.items():
        if isinstance(stats, dict):
            attacker_gain += float(stats.get("gain_paise", 0.0) or 0.0)

    honest = summary.get("honest") or {}
    honest_gain = float(honest.get("gain_paise", 0.0) or 0.0) if isinstance(honest, dict) else 0.0
    desc = get_scenario(scenario).description

    if not defenses:
        return (
            f"{desc} Defenses were OFF. Attacker-group welfare gain vs grid-only was "
            f"{attacker_gain:.0f} paise; honest participants gained {honest_gain:.0f} paise. "
            f"Flags logged (not fed into reputation): {flags or 'none'}."
        )

    defenses_note = {
        "sybil_farm": "Median quantity caps and reputation weighting limited Sybil volume; probation gates kept new identities from dominating matching.",
        "collusion_ring": "Collusion detector raised c_i on the ring and the reputation collusion weight cut their score growth.",
        "price_manipulation": "Reputation-weighted SDR and median caps blunted the price uplift from withheld supply.",
        "false_reports": "PV plausibility checks raised a_i on inflated reports, lowering honesty evidence.",
        "defect_after_trust": "Asymmetric kappa penalised under-delivery so Trusted status eroded after defection.",
    }.get(scenario, "Reputation gates and detectors limited attacker advantage.")

    return (
        f"{desc} Defenses were ON. Attacker-group welfare gain vs grid-only was "
        f"{attacker_gain:.0f} paise; honest participants gained {honest_gain:.0f} paise. "
        f"{defenses_note} Flags: {flags or 'none'}."
    )


def _attacker_profit(summary: dict[str, Any]) -> float:
    groups = summary.get("groups") or {}
    total = 0.0
    for stats in groups.values():
        if isinstance(stats, dict):
            total += float(stats.get("gain_paise", 0.0) or 0.0)
    return round(total, 2)


def _read_series(out: Path) -> list[dict[str, Any]]:
    intervals_path = out / "intervals.csv"
    fairness_path = out / "fairness.csv"
    reputation_path = out / "reputation.csv"
    by_t: dict[int, dict[str, Any]] = {}

    if intervals_path.is_file():
        with intervals_path.open(newline="") as f:
            for row in csv.DictReader(f):
                t = int(row["interval"])
                by_t[t] = {
                    "interval": t,
                    "p_ref": float(row["p_ref"]) if row.get("p_ref") not in (None, "") else None,
                    "sdr": float(row["sdr"]) if row.get("sdr") not in (None, "") else None,
                }

    if fairness_path.is_file():
        with fairness_path.open(newline="") as f:
            for row in csv.DictReader(f):
                t = int(row["interval"])
                pt = by_t.setdefault(t, {"interval": t})
                for key, src in (("jain", "jain"), ("gini", "gini_gain"), ("hhi", "hhi")):
                    raw = row.get(src)
                    if raw not in (None, ""):
                        try:
                            pt[key] = float(raw)
                        except ValueError:
                            pass

    # Mean reputation per interval from reputation.csv if present.
    if reputation_path.is_file():
        sums: dict[int, list[float]] = {}
        with reputation_path.open(newline="") as f:
            for row in csv.DictReader(f):
                t = int(row["interval"])
                try:
                    r = float(row.get("reputation") or row.get("R") or 0.0)
                except ValueError:
                    continue
                sums.setdefault(t, []).append(r)
        for t, vals in sums.items():
            pt = by_t.setdefault(t, {"interval": t})
            pt["mean_reputation"] = round(sum(vals) / len(vals), 6) if vals else None

    return [by_t[t] for t in sorted(by_t)]


def run_attack(scenario: str, params: dict[str, Any], defenses: bool) -> dict[str, Any]:
    if scenario not in ATTACK_SCENARIOS:
        raise ValueError(f"unsupported scenario: {scenario}")
    # Validate scenario exists in registry.
    get_scenario(scenario)

    participants = int(params.get("participants", _DEFAULTS["participants"]))
    days = int(params.get("days", _DEFAULTS["days"]))
    seed = int(params.get("seed", _DEFAULTS["seed"]))
    # Attack lab defaults to 24 intervals (~6h) so the UI stays responsive.
    max_intervals = int(params.get("max_intervals", 24))
    participants = max(10, min(participants, 200))
    days = max(1, min(days, 3))
    max_intervals = max(12, min(max_intervals, days * 96))

    cfg = SimConfig(
        scenario=scenario,
        participants=participants,
        days=days,
        seed=seed,
        defenses=defenses,
        mode="B3",
        max_intervals=max_intervals,
    )
    with tempfile.TemporaryDirectory(prefix="attack_lab_") as tmp:
        out = Path(tmp)
        summary = sim_run(cfg, out)
        series = _read_series(out)

    return {
        "summary": summary,
        "series": series,
        "attacker_profit_paise": _attacker_profit(summary),
        "plain_summary": _plain_summary(scenario, defenses, summary),
        "params_resolved": {
            "participants": participants,
            "days": days,
            "seed": seed,
            "max_intervals": max_intervals,
            **{
                k: v
                for k, v in params.items()
                if k not in ("participants", "days", "seed", "max_intervals")
            },
        },
    }
