"""Generate one Jupyter notebook per experiment (CSV → figure only)."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

NOTEBOOKS = [
    ("e1_honest", "E1 Honest baselines", "fig_e1"),
    ("e2_sybil", "E2 Sybil farm", "fig_e2"),
    ("e3_collusion", "E3 Collusion ring", "fig_e3"),
    ("e4_price_manipulation", "E4 Price manipulation", "fig_e4"),
    ("e5_false_reports", "E5 False reports", "fig_e5"),
    ("e6_defect", "E6 Defect after trust", "fig_e6"),
    ("e7_permanent_elite", "E7 Permanent elite", "fig_e7"),
    ("e8_grid_limits", "E8 Grid limits", "fig_e8"),
    ("e9_scalability", "E9 Scalability", "fig_e9"),
    ("e10_ablations", "E10 Ablations", "fig_e10"),
]


def nb(exp: str, title: str, fn: str) -> dict:
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                f"# {title}\n",
                "\n",
                "Reads only `results/phase11/"
                f"{exp}/metrics.csv`. Re-run the experiment script to refresh data;\n",
                "this notebook never calls the simulator.\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import sys\n",
                "from pathlib import Path\n",
                "ROOT = Path.cwd().resolve()\n",
                "if (ROOT / 'figures').is_dir():\n",
                "    sys.path.insert(0, str(ROOT / 'figures'))\n",
                "elif (ROOT / 'experiments' / 'figures').is_dir():\n",
                "    sys.path.insert(0, str(ROOT / 'experiments' / 'figures'))\n",
                "else:\n",
                "    sys.path.insert(0, str(ROOT.parent / 'figures'))\n",
                f"from plot_all import {fn}\n",
                f"{fn}()\n",
            ],
        },
    ]
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "cells": cells,
    }


def main() -> None:
    for exp, title, fn in NOTEBOOKS:
        path = HERE / f"{exp}.ipynb"
        path.write_text(json.dumps(nb(exp, title, fn), indent=1) + "\n")
        print("wrote", path.name)


if __name__ == "__main__":
    main()
