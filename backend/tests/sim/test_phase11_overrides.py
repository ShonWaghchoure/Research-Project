"""Phase 11 SimConfig overrides and ablation knobs."""

from __future__ import annotations

from pathlib import Path

from app.sim.runner import SimConfig, resolve_scenario, run


def test_resolve_scenario_sybil_override() -> None:
    cfg = SimConfig(scenario="sybil_farm", scenario_overrides={"sybil_count": 5})
    sc = resolve_scenario(cfg)
    assert sc.sybil_count == 5


def test_resolve_bot_param_withhold() -> None:
    cfg = SimConfig(
        scenario="price_manipulation",
        bot_param_overrides={"withhold": 0.5},
    )
    sc = resolve_scenario(cfg)
    assert sc.bots[0].params["withhold"] == 0.5


def test_ablation_smoke_runs(tmp_path: Path) -> None:
    cfg = SimConfig(
        scenario="honest",
        participants=12,
        days=1,
        seed=3,
        max_intervals=4,
        sign_meters=False,
        apply_median_cap=False,
        apply_lcb=False,
        apply_forgetting=False,
        apply_fairness_term=False,
        apply_collusion_detector=False,
    )
    summary = run(cfg, tmp_path / "abl")
    assert summary["intervals"] == 4
    assert (tmp_path / "abl" / "summary.json").exists() or (tmp_path / "abl" / "fairness.csv").exists()
