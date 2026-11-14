"""Read Phase 11 metrics.csv and emit publication-style figures.

Notebooks and CLI scripts import from here; they never re-run the simulator.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "phase11"
FIG_OUT = RESULTS / "figures"


def load_metrics(experiment: str) -> List[Dict[str, Any]]:
    path = RESULTS / experiment / "metrics.csv"
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}. Run: cd experiments && python {experiment}.py --smoke"
        )
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    # coerce numerics
    for row in rows:
        for k, v in list(row.items()):
            if v in ("", None):
                row[k] = None
                continue
            try:
                if v in ("True", "False"):
                    row[k] = v == "True"
                elif "." in v or "e" in v.lower():
                    row[k] = float(v)
                else:
                    row[k] = int(v)
            except (ValueError, AttributeError):
                pass
    return rows


def group_mean_ci(
    rows: Sequence[Dict[str, Any]],
    group_keys: Sequence[str],
    metric: str,
) -> List[Tuple[Tuple[Any, ...], float, float, int]]:
    """Return (key_tuple, mean, 95% CI half-width, n) for metric."""
    buckets: Dict[Tuple[Any, ...], List[float]] = defaultdict(list)
    for row in rows:
        if row.get(metric) is None:
            continue
        key = tuple(row.get(k) for k in group_keys)
        buckets[key].append(float(row[metric]))
    out = []
    for key, vals in sorted(buckets.items(), key=lambda x: x[0]):
        arr = np.asarray(vals, dtype=float)
        n = len(arr)
        mean = float(arr.mean())
        if n > 1:
            se = float(arr.std(ddof=1) / np.sqrt(n))
            ci = 1.96 * se
        else:
            ci = 0.0
        out.append((key, mean, ci, n))
    return out


def save_bar_ci(
    stats: Sequence[Tuple[Tuple[Any, ...], float, float, int]],
    *,
    title: str,
    ylabel: str,
    xlabel: str,
    out_name: str,
    xtick_fmt=None,
) -> Path:
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    labels = []
    means = []
    cis = []
    for key, mean, ci, _n in stats:
        labels.append(xtick_fmt(key) if xtick_fmt else str(key[0] if len(key) == 1 else key))
        means.append(mean)
        cis.append(ci)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(labels))
    ax.bar(x, means, yerr=cis, capsize=4, color="#2f6f4e", ecolor="#1a1a1a", alpha=0.9)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.axhline(0, color="#888", linewidth=0.8)
    fig.tight_layout()
    out = FIG_OUT / out_name
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"wrote {out}")
    return out


def require_matplotlib() -> None:
    # Imported at module level; this exists so notebooks can call an explicit check.
    import matplotlib  # noqa: F401
