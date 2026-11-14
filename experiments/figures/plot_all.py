"""Regenerate every Phase 11 figure from saved metrics.csv files.

    cd experiments && python figures/plot_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from plot_utils import group_mean_ci, load_metrics, save_bar_ci  # noqa: E402


def fig_e1() -> None:
    rows = load_metrics("e1_honest")
    # Prefer n=100 if present, else whatever is in the CSV.
    ns = sorted({r["n"] for r in rows if r.get("n") is not None})
    n = 100 if 100 in ns else ns[0]
    subset = [r for r in rows if r.get("n") == n]
    stats = group_mean_ci(subset, ["mode"], "bill_saving_pct")
    save_bar_ci(
        stats,
        title=f"E1 Honest baselines — buyer bill saving (n={n})",
        ylabel="Buyer bill saving (%)",
        xlabel="Baseline",
        out_name="e1_bill_saving.png",
        xtick_fmt=lambda k: str(k[0]),
    )
    stats = group_mean_ci(subset, ["mode"], "revenue_uplift_pct")
    save_bar_ci(
        stats,
        title=f"E1 Honest baselines — seller revenue uplift (n={n})",
        ylabel="Seller revenue uplift (%)",
        xlabel="Baseline",
        out_name="e1_revenue_uplift.png",
        xtick_fmt=lambda k: str(k[0]),
    )


def fig_e2() -> None:
    rows = load_metrics("e2_sybil")
    metric = "group_sybil_farm_gain_paise"
    if not any(r.get(metric) is not None for r in rows):
        metric = "gain_paise"
    stats = group_mean_ci(rows, ["sybil_count", "defenses"], metric)
    save_bar_ci(
        stats,
        title="E2 Sybil farm — attacker-group gain",
        ylabel="Attacker-group gain (paise)",
        xlabel="(sybils, defenses)",
        out_name="e2_attacker_gain.png",
        xtick_fmt=lambda k: f"k={k[0]}, d={'on' if k[1] else 'off'}",
    )


def fig_e3() -> None:
    rows = load_metrics("e3_collusion")
    metric = "flag_collusion" if any(r.get("flag_collusion") is not None for r in rows) else "reputation_gini_end"
    stats = group_mean_ci(rows, ["ring_size", "detection"], metric)
    save_bar_ci(
        stats,
        title="E3 Collusion ring — detection / inequality",
        ylabel=metric,
        xlabel="(ring size, detection)",
        out_name="e3_detection.png",
        xtick_fmt=lambda k: f"r={k[0]}, det={'on' if k[1] else 'off'}",
    )


def fig_e4() -> None:
    rows = load_metrics("e4_price_manipulation")
    metric = "group_manipulator_gain_paise"
    if not any(r.get(metric) is not None for r in rows):
        metric = "gain_paise"
    stats = group_mean_ci(rows, ["withhold", "defenses"], metric)
    save_bar_ci(
        stats,
        title="E4 Price manipulation — seller-group gain",
        ylabel="Gain (paise)",
        xlabel="(withhold, defenses)",
        out_name="e4_seller_gain.png",
        xtick_fmt=lambda k: f"w={k[0]}, d={'on' if k[1] else 'off'}",
    )


def fig_e5() -> None:
    rows = load_metrics("e5_false_reports")
    metric = "flag_false_report" if any(r.get("flag_false_report") is not None for r in rows) else "reputation_gini_end"
    stats = group_mean_ci(rows, ["inflate", "defenses"], metric)
    save_bar_ci(
        stats,
        title="E5 False reports — flags / inequality",
        ylabel=metric,
        xlabel="(inflate, defenses)",
        out_name="e5_detection.png",
        xtick_fmt=lambda k: f"i={k[0]}, d={'on' if k[1] else 'off'}",
    )


def fig_e6() -> None:
    rows = load_metrics("e6_defect")
    stats = group_mean_ci(rows, ["n"], "gain_paise")
    save_bar_ci(
        stats,
        title="E6 Defect after trust — market welfare gain",
        ylabel="Gain (paise)",
        xlabel="Participants",
        out_name="e6_welfare.png",
        xtick_fmt=lambda k: str(k[0]),
    )


def fig_e7() -> None:
    rows = load_metrics("e7_permanent_elite")
    stats = group_mean_ci(rows, ["forgetting"], "reputation_gini_end")
    save_bar_ci(
        stats,
        title="E7 Permanent elite — end reputation Gini",
        ylabel="Reputation Gini",
        xlabel="Forgetting",
        out_name="e7_rep_gini.png",
        xtick_fmt=lambda k: "on" if k[0] else "off",
    )


def fig_e8() -> None:
    rows = load_metrics("e8_grid_limits")
    stats = group_mean_ci(rows, ["capacity_kw"], "p2p_line_violations")
    save_bar_ci(
        stats,
        title="E8 Grid limits — P2P-caused line violations",
        ylabel="P2P line violations (count)",
        xlabel="Feeder capacity (kW)",
        out_name="e8_violations.png",
        xtick_fmt=lambda k: str(k[0]),
    )


def fig_e9() -> None:
    rows = load_metrics("e9_scalability")
    stats = group_mean_ci(rows, ["n"], "mean_clear_ms")
    save_bar_ci(
        stats,
        title="E9 Scalability — mean clearing time",
        ylabel="Clearing time (ms / interval)",
        xlabel="Participants",
        out_name="e9_clear_ms.png",
        xtick_fmt=lambda k: str(k[0]),
    )


def fig_e10() -> None:
    rows = load_metrics("e10_ablations")
    stats = group_mean_ci(rows, ["ablation"], "gain_paise")
    save_bar_ci(
        stats,
        title="E10 Ablations — market welfare gain",
        ylabel="Gain (paise)",
        xlabel="Ablation",
        out_name="e10_ablations.png",
        xtick_fmt=lambda k: str(k[0]),
    )


FIGURES = [
    ("e1_honest", fig_e1),
    ("e2_sybil", fig_e2),
    ("e3_collusion", fig_e3),
    ("e4_price_manipulation", fig_e4),
    ("e5_false_reports", fig_e5),
    ("e6_defect", fig_e6),
    ("e7_permanent_elite", fig_e7),
    ("e8_grid_limits", fig_e8),
    ("e9_scalability", fig_e9),
    ("e10_ablations", fig_e10),
]


def main() -> int:
    only = sys.argv[1:]
    for name, fn in FIGURES:
        if only and name not in only and name.split("_")[0] not in only:
            continue
        try:
            fn()
        except FileNotFoundError as exc:
            print(f"skip {name}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
