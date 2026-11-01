#!/usr/bin/env python3
"""Plot the paper's condition-specific JSEL-minus-JFAST effects.

Read paired means and marginal 95% seed-bootstrap intervals from the stored
analysis and render the nine condition-specific contrasts."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONDITIONS = [(load, dose) for load in (0.60, 0.80, 0.95) for dose in (1, 4, 10)]
COLOR = "#263e50"


def read_contrasts(path: Path) -> list[dict]:
    """Select the nine paired contrasts without changing their scale or order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    selected = {}
    for row in data["contrasts"]:
        if row["comparison"] != "P3-P2":
            continue
        key = (row["load"], row["missions"])
        if key in selected:
            raise ValueError(f"Duplicate JSEL-minus-JFAST condition: {key}")
        for metric in ("time_s", "A_vh"):
            estimate = row["metrics"][metric]
            values = [estimate[field] for field in ("lo", "mean", "hi")]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Non-finite estimate for {key}, {metric}")
            if not values[0] <= values[1] <= values[2] or estimate["n"] != 48:
                raise ValueError(f"Unexpected interval or seed count for {key}, {metric}")
        selected[key] = row
    if set(selected) != set(CONDITIONS):
        raise ValueError("Expected all nine published load/dose conditions")
    return [selected[key] for key in CONDITIONS]


def plot_results(rows: list[dict], output: Path, dpi: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    style = {
        "font.family": "DejaVu Serif",
        "font.size": 7.3,
        "axes.titlesize": 8.2,
        "axes.labelsize": 8.2,
        "axes.linewidth": 0.6,
        "xtick.labelsize": 7.3,
        "ytick.labelsize": 7.3,
        "xtick.major.size": 3.5,
        "ytick.major.size": 3.5,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
    }
    panels = [
        (
            "time_s", "(a) Ambulance duration difference (s)",
            [-1.35, 28.55], [0, 5, 10, 15, 20, 25],
        ),
        (
            "A_vh", "(b) Spatial exposure difference (veh-h)",
            [-13.55, 1.20], [-12, -10, -8, -6, -4, -2, 0],
        ),
    ]
    labels = [f"{load:.2f} / {dose}" for load, dose in CONDITIONS]
    positions = list(range(len(rows)))

    with plt.rc_context(style):
        figure, axes = plt.subplots(2, 1, figsize=(3.43, 5.0))
        figure.subplots_adjust(left=0.25, right=0.96, top=0.95, bottom=0.17, hspace=0.52)
        for axis, (metric, title, limits, ticks) in zip(axes, panels):
            estimates = [row["metrics"][metric] for row in rows]
            means = [estimate["mean"] for estimate in estimates]
            errors = [
                [estimate["mean"] - estimate["lo"] for estimate in estimates],
                [estimate["hi"] - estimate["mean"] for estimate in estimates],
            ]
            axis.errorbar(
                means, positions, xerr=errors, fmt="o", color=COLOR,
                markersize=3.2, elinewidth=1.0, capsize=2.0, capthick=1.0,
            )
            axis.set_yticks(positions, labels)
            axis.set_ylim(len(rows) - 0.4, -0.6)
            axis.set_xlim(limits)
            axis.set_xticks(ticks)
            axis.set_title(title, loc="left", pad=7)
            axis.set_ylabel("Load / missions")
            axis.set_xlabel("JSEL minus JFAST", labelpad=4)
            axis.set_axisbelow(True)
            axis.grid(axis="x", color="#dedede", linewidth=0.5)
            axis.axvline(0, color="#777777", linewidth=0.6)
            axis.spines[["top", "right"]].set_visible(False)

        axes[0].axvline(20, color="#444444", linestyle="--", linewidth=0.8)
        axes[0].text(
            20.35, 0.985, "20 s tolerance", transform=axes[0].get_xaxis_transform(),
            ha="left", va="top", fontsize=6.1, color="#444444",
        )
        figure.text(
            0.5, 0.025, "Points: paired means; bars: 95% bootstrap intervals.\n"
            "48 paired seeds per condition; intervals are marginal.",
            ha="center", va="bottom", fontsize=6.1,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output, dpi=dpi, facecolor="white")
        plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "work/v9/sumo_analysis.json",
        help="Stored condition means and confidence intervals",
    )
    parser.add_argument(
        "--output", type=Path, default=HERE / "figures/primary_effects.png",
        help="Output image (default: paper/figures/primary_effects.png)",
    )
    parser.add_argument("--dpi", type=int, default=360, help="Raster resolution (default: 360)")
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    rows = read_contrasts(args.input)
    plot_results(rows, args.output, args.dpi)
    print(f"Wrote {args.output.resolve()} from nine paired contrasts")


if __name__ == "__main__":
    main()
