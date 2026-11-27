"""One plotting style for every figure in the research outputs."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK = "#1f2430"
MUTED = "#8a90a0"
GRID = "#e6e8ee"
ACCENT = "#5b5bd6"      # top-tier / main series
SECOND = "#e5484d"
THIRD = "#30a46c"
FOURTH = "#f5a524"
SERIES = [ACCENT, SECOND, THIRD, FOURTH, "#0ea5e9", "#a855f7"]

plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "axes.edgecolor": GRID,
    "axes.labelcolor": INK, "axes.titlecolor": INK, "axes.titleweight": "bold", "axes.titlesize": 11,
    "axes.labelsize": 9, "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "legend.frameon": False, "legend.fontsize": 8, "font.size": 9,
})


def figure(width: float = 6.4, height: float = 3.6, ncols: int = 1):
    fig, axes = plt.subplots(1, ncols, figsize=(width, height))
    return fig, axes


def close_all() -> None:
    plt.close("all")
