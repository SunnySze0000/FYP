"""W3 · Does unusual wallet activity this hour warn of a probability jump next hour?"""

from __future__ import annotations

import numpy as np
import pandas as pd

from walletlens.analytics.calibration import sigmoid
from walletlens.research import plots
from walletlens.research.result import ExperimentResult
from walletlens.topics.events.wallet_context import WalletContext


def _features(hours: pd.DataFrame) -> pd.DataFrame:
    frame = hours.sort_values(["market_id", "ts"]).copy()
    by_market = frame.groupby("market_id")

    def relative(column: str) -> pd.Series:
        level = np.log1p(frame[column].abs())
        trailing = level.groupby(frame["market_id"]).transform(lambda s: s.shift(1).rolling(48, min_periods=12).mean())
        return level - trailing

    frame["abs_dp"] = frame["dp"].abs()
    frame["recent_vol"] = by_market["dp"].transform(lambda s: s.abs().shift(1).rolling(24, min_periods=6).mean())
    frame["gross_z"] = relative("f_gross")
    frame["whale_z"] = relative("f_whale_gross")
    frame["wallets_z"] = relative("f_wallets")
    frame["new_z"] = relative("f_new_gross")
    frame["imbalance"] = (frame["f_all"].abs() / frame["f_gross"].replace(0, np.nan)).fillna(0)
    return frame


def _fit_logistic(x: np.ndarray, y: np.ndarray, iterations: int = 50) -> np.ndarray:
    x = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        mu = sigmoid(x @ beta)
        w = np.clip(mu * (1 - mu), 1e-9, None)
        step = np.linalg.solve(x.T @ (x * w[:, None]) + 1e-3 * np.eye(len(beta)), x.T @ (y - mu) - 1e-3 * beta)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def _auc(score: np.ndarray, y: np.ndarray) -> float:
    ranks = pd.Series(score).rank().to_numpy()
    positives = y.sum()
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return np.nan
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def run(ctx: WalletContext) -> ExperimentResult:
    frame = _features(ctx.hours)
    base_cols = ["abs_dp", "recent_vol"]
    wallet_cols = ["gross_z", "whale_z", "wallets_z", "new_z", "imbalance"]
    frame = frame.dropna(subset=base_cols + wallet_cols + ["shock_next"])
    cut = ctx.markets.set_index("market_id")["close_ts"].astype("int64")
    frame["late"] = frame["market_id"].map(cut) > ctx.split_ts               # out-of-time test: later-closing markets
    train, test = frame[~frame["late"]], frame[frame["late"]]
    y_train, y_test = train["shock_next"].to_numpy(float), test["shock_next"].to_numpy(float)
    if len(train) < 1000 or len(test) < 1000 or y_test.sum() < 30:
        return ExperimentResult(id="w3", title="Early warning", verdict="inconclusive",
                                headline="Too few hours or jumps to fit and test the early-warning model.",
                                question="Does unusual wallet activity this hour warn of a jump next hour?",
                                metrics={"train_hours": int(len(train)), "test_hours": int(len(test))})

    def standardise(cols):
        mean, std = train[cols].mean(), train[cols].std().replace(0, 1)
        return ((train[cols] - mean) / std).to_numpy(), ((test[cols] - mean) / std).to_numpy()

    xb_tr, xb_te = standardise(base_cols)
    xf_tr, xf_te = standardise(base_cols + wallet_cols)
    score_base = np.column_stack([np.ones(len(xb_te)), xb_te]) @ _fit_logistic(xb_tr, y_train)
    beta_full = _fit_logistic(xf_tr, y_train)
    score_full = np.column_stack([np.ones(len(xf_te)), xf_te]) @ beta_full
    auc_base, auc_full = _auc(score_base, y_test), _auc(score_full, y_test)
    rng = np.random.default_rng(ctx.cfg.seed)
    markets = test["market_id"].to_numpy()
    keys = np.unique(markets)
    rows = {k: np.nonzero(markets == k)[0] for k in keys}
    gains = []
    for _ in range(min(ctx.cfg.bootstrap_draws, 500)):
        pick = np.concatenate([rows[k] for k in rng.choice(keys, len(keys))])
        gains.append(_auc(score_full[pick], y_test[pick]) - _auc(score_base[pick], y_test[pick]))
    gains = np.array([g for g in gains if np.isfinite(g)])
    gain = auc_full - auc_base
    low, high = float(np.quantile(gains, 0.025)), float(np.quantile(gains, 0.975))
    verdict = "pass" if low > 0 else "fail"
    # how much more often does a jump follow the most unusual 5% of wallet-activity hours?
    top = test[score_full >= np.quantile(score_full, 0.95)]
    lift = float(top["shock_next"].mean() / max(test["shock_next"].mean(), 1e-9))

    fig, ax = plots.figure(6, 3.4)
    ax.bar(["price only", "price + wallets"], [auc_base, auc_full], color=[plots.MUTED, plots.ACCENT], width=0.5)
    ax.set_ylim(0.5, max(auc_full, auc_base) + 0.05)
    ax.set_ylabel("AUC, later markets")
    ax.set_title("Predicting next hour's jump")
    coefficients = dict(zip(["intercept"] + base_cols + wallet_cols, np.round(beta_full, 4).tolist()))
    headline = (f"Out of time, adding wallet activity moves the AUC from {auc_base:.3f} to {auc_full:.3f} "
                f"(gain {gain:+.3f}, 95% CI {low:+.3f} to {high:+.3f}); the 5% most unusual hours are followed by a jump "
                f"{lift:.1f}× as often as average.")
    return ExperimentResult(
        id="w3", title="Early warning", verdict=verdict, headline=headline,
        question="Does unusual wallet activity this hour warn of a probability jump next hour, beyond recent price moves?",
        metrics={"auc_price_only": auc_base, "auc_with_wallets": auc_full, "gain": gain, "low": low, "high": high,
                 "top5pct_lift": lift, "coefficients": coefficients, "train_hours": int(len(train)),
                 "test_hours": int(len(test)), "test_jumps": int(y_test.sum())},
        figures={"early_warning": fig},
        notes=["Trained on earlier-closing markets, tested on later-closing ones.",
               "Pass rule (pre-registered): AUC gain over the price-only model > 0 with the 95% CI above 0 (markets resampled)."])
