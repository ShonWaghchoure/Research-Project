"""End-to-end simulator tests (Phase 4 acceptance and scenario sanity)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.sim import scenarios
from app.sim.cli import main
from app.sim.runner import SimConfig, run

DETERMINISTIC = ["intervals.csv", "trades.csv", "reputation.csv", "flags.csv", "fairness.csv", "participants.csv", "summary.json"]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def test_same_seed_gives_identical_outputs(tmp_path: Path) -> None:
    cfg = SimConfig(scenario="lazy", participants=20, days=1, seed=11)
    run(cfg, tmp_path / "a")
    run(cfg, tmp_path / "b")
    for name in DETERMINISTIC:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    cfg_a = json.loads((tmp_path / "a" / "config.json").read_text())
    assert cfg_a["git"]["commit"]  # git commit recorded
    assert cfg_a["sim"]["seed"] == 11


def test_different_seed_differs(tmp_path: Path) -> None:
    run(SimConfig(participants=15, days=1, seed=1, sign_meters=False), tmp_path / "a")
    run(SimConfig(participants=15, days=1, seed=2, sign_meters=False), tmp_path / "b")
    assert (tmp_path / "a" / "intervals.csv").read_bytes() != (tmp_path / "b" / "intervals.csv").read_bytes()


def test_100_participant_honest_day_respects_line_limits(tmp_path: Path) -> None:
    summary = run(SimConfig(participants=100, days=1, seed=42), tmp_path)
    assert summary["line_violations"] == 0
    assert summary["p2p_line_violations"] == 0
    rows = _rows(tmp_path / "intervals.csv")
    assert len(rows) == 96
    assert all(int(r["line_violations"]) == 0 for r in rows)
    assert all(int(r["readings_failed"]) == 0 for r in rows)
    assert sum(int(r["readings_verified"]) for r in rows) > 0
    assert sum(int(r["matched_wh"]) for r in rows) > 0  # the market actually trades


def test_grid_tight_p2p_never_causes_overload(tmp_path: Path) -> None:
    """On an 8 kW feeder household load alone overloads lines (B0 shows it). B3 must never add
    to an overload, and P2P should relieve the grid relative to grid-only."""
    b3 = run(SimConfig(scenario="grid_tight", participants=60, days=1, seed=3, sign_meters=False), tmp_path / "b3")
    b0 = run(SimConfig(scenario="grid_tight", participants=60, days=1, seed=3, sign_meters=False, mode="B0"), tmp_path / "b0")
    assert b3["p2p_line_violations"] == 0
    assert b0["line_violations"] > 0
    assert b3["line_violations"] <= b0["line_violations"]


def test_lazy_bots_end_with_lower_reputation(tmp_path: Path) -> None:
    summary = run(SimConfig(scenario="lazy", participants=40, days=2, seed=5, sign_meters=False), tmp_path)
    rep = summary["mean_final_reputation_by_bot"]
    assert rep["lazy"] < rep["honest"]


def test_buyer_bills_lower_than_grid_only(tmp_path: Path) -> None:
    """Acceptance sanity check: B1, B2, B3 buyer bills are below B0 (not a research claim)."""
    bills = {}
    for mode in ("B0", "B1", "B2", "B3"):
        s = run(SimConfig(participants=30, days=1, seed=9, mode=mode, sign_meters=False), tmp_path / mode)
        bills[mode] = s["market"]["bill_paise"]
    assert bills["B0"] == pytest.approx(run(SimConfig(participants=30, days=1, seed=9, mode="B0", sign_meters=False), tmp_path / "B0b")["market"]["grid_only_bill_paise"])
    for mode in ("B1", "B2", "B3"):
        assert bills[mode] < bills["B0"], mode


def test_collusion_ring_is_flagged_and_loses_reputation_with_defenses(tmp_path: Path) -> None:
    on = run(SimConfig(scenario="collusion_ring", participants=30, days=2, seed=4, sign_meters=False), tmp_path / "on")
    off = run(SimConfig(scenario="collusion_ring", participants=30, days=2, seed=4, defenses=False, sign_meters=False), tmp_path / "off")
    flagged = {pid for r in _rows(tmp_path / "on" / "flags.csv") if r["kind"] == "collusion" for pid in r["participant_ids"].split(";")}
    ring = {r["participant_id"] for r in _rows(tmp_path / "on" / "participants.csv") if r["bot"] == "ring"}
    assert ring <= flagged
    assert on["mean_final_reputation_by_bot"]["ring"] < off["mean_final_reputation_by_bot"]["ring"]


def test_reveal_misses_are_penalised(tmp_path: Path) -> None:
    s = run(SimConfig(scenario="non_revealer", participants=40, days=1, seed=8, sign_meters=False), tmp_path)
    rep = s["mean_final_reputation_by_bot"]
    assert rep["non_revealer"] < rep["honest"]


@pytest.mark.parametrize("name", scenarios.names())
def test_every_scenario_runs(tmp_path: Path, name: str) -> None:
    s = run(SimConfig(scenario=name, participants=16, days=1, seed=1, sign_meters=False), tmp_path)
    assert s["p2p_line_violations"] == 0
    for f in DETERMINISTIC + ["config.json", "timing.csv"]:
        assert (tmp_path / f).exists(), f


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scenarios"]) == 0
    assert "sybil_farm" in capsys.readouterr().out
    out = tmp_path / "cli"
    assert main(["simulate", "--scenario", "honest", "--participants", "10", "--days", "1", "--seed", "1", "--no-sign", "--out", str(out)]) == 0
    assert (out / "summary.json").exists()
