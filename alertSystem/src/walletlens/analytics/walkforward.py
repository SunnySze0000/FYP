"""Expanding-window, walk-forward linear models by day, and out-of-sample comparisons.

Every day ``d`` is predicted by an OLS fitted on all earlier days only. Fits use running
sums of X'X and X'y per day, so the cost is linear in the number of days.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def walk_forward(frame: pd.DataFrame, target: str, models: dict[str, list[str]], min_train_days: int,
                 day: str = "day", ridge: float = 1e-8) -> pd.DataFrame:
    """Return ``frame`` rows from testable days with an out-of-sample prediction column per model."""
    frame = frame.dropna(subset=[target] + sorted({c for cols in models.values() for c in cols}))
    days = np.sort(frame[day].unique())
    groups = frame.groupby(day).indices
    outputs = []
    sums = {name: None for name in models}
    for position, d in enumerate(days):
        rows = frame.iloc[groups[d]]
        y = rows[target].to_numpy(float)
        result = rows[[day, target]].copy()
        testable = position >= min_train_days
        for name, columns in models.items():
            x = np.column_stack([np.ones(len(rows))] + [rows[c].to_numpy(float) for c in columns])
            if testable and sums[name] is not None:
                xtx, xty = sums[name]
                beta = np.linalg.solve(xtx + ridge * np.eye(len(xtx)), xty)
                result[f"pred_{name}"] = x @ beta
            contribution = (x.T @ x, x.T @ y)
            sums[name] = contribution if sums[name] is None else (sums[name][0] + contribution[0],
                                                                  sums[name][1] + contribution[1])
        if testable:
            outputs.append(result)
    if not outputs:
        return pd.DataFrame()
    return pd.concat(outputs)


def final_coefficients(frame: pd.DataFrame, target: str, columns: list[str]) -> dict:
    frame = frame.dropna(subset=[target] + columns)
    x = np.column_stack([np.ones(len(frame))] + [frame[c].to_numpy(float) for c in columns])
    beta, *_ = np.linalg.lstsq(x, frame[target].to_numpy(float), rcond=None)
    return dict(zip(["intercept"] + columns, beta.tolist()))


def r2_gain(predictions: pd.DataFrame, target: str, model: str, baseline: str, draws: int, seed: int,
            day: str = "day") -> dict:
    """Out-of-sample R² gain of ``model`` over ``baseline`` (1 - SSE_m / SSE_b), CI by resampling days."""
    y = predictions[target].to_numpy(float)
    per_day = pd.DataFrame({
        "day": predictions[day].to_numpy(),
        "sse_m": (y - predictions[f"pred_{model}"].to_numpy(float)) ** 2,
        "sse_b": (y - predictions[f"pred_{baseline}"].to_numpy(float)) ** 2,
        "sst": (y - y.mean()) ** 2,
    }).groupby("day").sum()
    if per_day.empty:
        return {"gain": np.nan, "low": np.nan, "high": np.nan, "days": 0, "r2_model": np.nan, "r2_baseline": np.nan}
    sse_m, sse_b, sst = per_day["sse_m"].to_numpy(), per_day["sse_b"].to_numpy(), per_day["sst"].to_numpy()
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(per_day), size=(draws, len(per_day)))
    boot = 1 - sse_m[picks].sum(axis=1) / sse_b[picks].sum(axis=1)
    gain = 1 - sse_m.sum() / sse_b.sum()
    return {"gain": float(gain), "low": float(np.quantile(boot, 0.025)), "high": float(np.quantile(boot, 0.975)),
            "days": int(len(per_day)), "rows": int(len(predictions)),
            "r2_model": float(1 - sse_m.sum() / sst.sum()), "r2_baseline": float(1 - sse_b.sum() / sst.sum()),
            "p_gain_le_0": float(np.mean(boot <= 0))}


def daily_ic(frame: pd.DataFrame, signal: str, target: str, draws: int, seed: int, day: str = "day") -> dict:
    """Mean per-day Spearman correlation between a signal and the target, CI by resampling days."""
    values = []
    for _, part in frame.dropna(subset=[signal, target]).groupby(day):
        if len(part) >= 10 and part[signal].nunique() > 1:
            values.append(part[signal].rank().corr(part[target].rank()))
    values = np.array([v for v in values if np.isfinite(v)])
    if len(values) == 0:
        return {"ic": np.nan, "low": np.nan, "high": np.nan, "days": 0}
    rng = np.random.default_rng(seed)
    boot = values[rng.integers(0, len(values), size=(draws, len(values)))].mean(axis=1)
    return {"ic": float(values.mean()), "low": float(np.quantile(boot, 0.025)),
            "high": float(np.quantile(boot, 0.975)), "days": int(len(values))}
