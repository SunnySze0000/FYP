"""EventLens five-stage SPY forecasting experiment.

Stages:
1. Get data
2. Extract features
3. Analyze correlations
4. Fit models
5. Compare models

The script mirrors the annotated notebook. It uses only information available
on or before each forecast date and never uses final_outcome as a feature.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


# ============================================================================
# 1. GET DATA
# ============================================================================

ROOT = Path(__file__).resolve().parents[1]
PROBABILITY_PATH = ROOT / "datasets" / "forward_probabilities.csv"
MARKET_PATH = ROOT / "datasets" / "index_daily.csv"
RESULTS_PATH = ROOT / "models" / "forecast_model_results.csv"
CORRELATIONS_PATH = ROOT / "models" / "feature_return_correlations.csv"
HORIZONS = (1, 5, 20)
SEED = 42

OUTCOME_MOVE = {
    "25 bps decrease": -25.0,
    "50+ bps decrease": -50.0,
    "50 bps decrease": -50.0,
    "75+ bps decrease": -75.0,
    "25 bps increase": 25.0,
    "25+ bps increase": 50.0,
    "50 bps increase": 50.0,
    "50+ bps increase": 50.0,
    "75 bps increase": 75.0,
    "no change": 0.0,
}


def load_data():
    """Load SPY prices and prediction-market snapshots."""
    market = pd.read_csv(MARKET_PATH, parse_dates=["date"])
    market = market.loc[market["ticker"].eq("SPY")].sort_values("date").copy()
    market["return_1d"] = pd.to_numeric(market["return_1d"], errors="coerce")
    market["close"] = pd.to_numeric(market["close"], errors="coerce")
    market = market.dropna(subset=["close", "return_1d"])
    market["date"] = market["date"].dt.tz_localize(None).dt.normalize()

    probability = pd.read_csv(PROBABILITY_PATH, parse_dates=["date"])
    probability["date"] = probability["date"].dt.tz_localize(None).dt.normalize()
    probability["move"] = probability["outcome"].map(OUTCOME_MOVE)
    probability = probability.dropna(subset=["move"]).copy()
    return market, probability


# ============================================================================
# 2. EXTRACT FEATURES
# ============================================================================

def extract_event_features(probability):
    """Create point-in-time features from the nearest available meeting.

    Each date keeps the smallest available horizon. `final_outcome` is not
    used: it is only known after the meeting and would leak future information.
    """
    chosen = (
        probability.sort_values(["date", "horizon_month"])
        .groupby("date", as_index=False)
        .first()
    )
    selected = probability.merge(
        chosen[["date", "horizon_month"]],
        on=["date", "horizon_month"],
        how="inner",
    )
    selected["market_probability"] = pd.to_numeric(
        selected["market_probability"], errors="coerce"
    )
    selected = selected.dropna(subset=["market_probability"])
    selected["outcome_group"] = np.select(
        [
            selected["move"] < 0,
            selected["move"] > 0,
            selected["move"].eq(0),
        ],
        ["decrease", "increase", "no_change"],
        default="other",
    )
    selected["total_probability"] = selected.groupby("date")[
        "market_probability"
    ].transform("sum")
    selected["p"] = selected["market_probability"] / selected["total_probability"]

    # Probability features: each has a different interpretation.
    selected["weighted_move"] = selected["p"] * selected["move"]
    selected["weighted_abs_move"] = selected["p"] * selected["move"].abs()
    selected["weighted_square_move"] = selected["p"] * selected["move"].pow(2)
    selected["entropy_part"] = -selected["p"] * np.log(
        selected["p"].clip(lower=1e-12)
    )

    event = selected.groupby("date", as_index=False).agg(
        event_id=("event_id", "first"),
        horizon_month=("horizon_month", "first"),
        expected_move=("weighted_move", "sum"),
        expected_abs_move=("weighted_abs_move", "sum"),
        expected_square_move=("weighted_square_move", "sum"),
        entropy=("entropy_part", "sum"),
        max_probability=("p", "max"),
        outcome_count=("p", "size"),
        probability_increase=("p", lambda values: values[
            selected.loc[values.index, "outcome_group"].eq("increase")
        ].sum()),
        probability_decrease=("p", lambda values: values[
            selected.loc[values.index, "outcome_group"].eq("decrease")
        ].sum()),
        probability_no_change=("p", lambda values: values[
            selected.loc[values.index, "outcome_group"].eq("no_change")
        ].sum()),
    )
    event["move_variance"] = (
        event["expected_square_move"] - event["expected_move"].pow(2)
    ).clip(lower=0)
    event = event.sort_values("date")
    event["expected_move_change"] = event["expected_move"].diff()
    event["max_probability_change"] = event["max_probability"].diff()
    return event


def add_market_features(market):
    """Create history inputs and future targets.

    History features are shifted by one trading day. Thus a prediction at the
    end of day t cannot accidentally use the return from day t as an input.
    Targets begin on the next trading day.
    """
    frame = market.sort_values("date").copy()
    returns = frame["return_1d"]
    frame["history_return_1d"] = returns.shift(1)
    frame["history_return_5d"] = returns.shift(1).rolling(5).mean()
    frame["history_return_20d"] = returns.shift(1).rolling(20).mean()
    frame["history_variance_5d"] = returns.shift(1).pow(2).rolling(5).mean()
    frame["history_variance_20d"] = returns.shift(1).pow(2).rolling(20).mean()

    for horizon in HORIZONS:
        future_returns = [
            returns.shift(-step) for step in range(1, horizon + 1)
        ]
        frame[f"target_return_{horizon}d"] = (
            frame["close"].shift(-horizon) / frame["close"] - 1
        )
        frame[f"target_variance_{horizon}d"] = sum(
            value.pow(2) for value in future_returns
        )
    return frame


def build_model_data(market, probability):
    event = extract_event_features(probability)
    frame = add_market_features(market)
    return pd.merge_asof(
        frame.sort_values("date"),
        event.sort_values("date"),
        on="date",
        direction="backward",
    ).dropna(subset=["expected_move"])


# ============================================================================
# 3. ANALYZE CORRELATIONS
# ============================================================================

EVENT_FEATURES = [
    "expected_move",
    "expected_abs_move",
    "move_variance",
    "entropy",
    "max_probability",
    "probability_increase",
    "probability_decrease",
    "probability_no_change",
    "expected_move_change",
    "max_probability_change",
    "horizon_month",
    "outcome_count",
]
HISTORY_FEATURES = [
    "history_return_1d",
    "history_return_5d",
    "history_return_20d",
    "history_variance_5d",
    "history_variance_20d",
]
ALL_FEATURES = HISTORY_FEATURES + EVENT_FEATURES


def analyze_correlations(model_data):
    """Calculate exploratory Spearman feature/target correlations."""
    targets = [
        f"target_return_{horizon}d" for horizon in HORIZONS
    ]
    correlations = model_data[EVENT_FEATURES + targets].corr(method="spearman")
    return correlations.loc[EVENT_FEATURES, targets]


# ============================================================================
# 4. FIT MODELS
# ============================================================================

def qlike(actual, predicted):
    """QLIKE for non-negative variance; predictions are floored for scoring."""
    actual = np.maximum(actual, 1e-8)
    predicted = np.maximum(predicted, 1e-8)
    return np.mean(actual / predicted - np.log(actual / predicted) - 1)


def fit_model(train, test, features, target, is_variance):
    """Fit standardized Ridge and return held-out metrics."""
    train = train.dropna(subset=features + [target])
    test = test.dropna(subset=features + [target])
    estimator = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    estimator.fit(train[features], train[target])
    prediction = estimator.predict(test[features])
    actual = test[target].to_numpy()
    result = {
        "mae": mean_absolute_error(actual, prediction),
        "rmse": mean_squared_error(actual, prediction) ** 0.5,
        "r2": r2_score(actual, prediction),
        "negative_prediction_rate": np.mean(prediction < 0),
        "rows": len(test),
    }
    if is_variance:
        result["qlike"] = qlike(actual, prediction)
    return result


def fit_all_models(model_data):
    """Fit history-only, event-only, and combined models.

    Event-only return is included to answer whether event probabilities have
    predictive value by themselves, without recent SPY history.
    """
    results = []
    model_features = {
        "history_only": HISTORY_FEATURES,
        "event_only": EVENT_FEATURES,
        "history_plus_event": ALL_FEATURES,
    }
    for horizon in HORIZONS:
        usable = model_data.dropna(
            subset=[
                f"target_return_{horizon}d",
                f"target_variance_{horizon}d",
            ]
        ).iloc[::horizon].reset_index(drop=True)
        split = int(len(usable) * 0.70)
        train, test = usable.iloc[:split], usable.iloc[split:]
        for target_kind, is_variance in [("return", False), ("variance", True)]:
            target = f"target_{target_kind}_{horizon}d"
            candidates = model_features.items()
            if target_kind == "variance":
                candidates = [
                    ("history_only", HISTORY_FEATURES),
                    ("history_plus_event", ALL_FEATURES),
                ]
            for model_name, features in candidates:
                metrics = fit_model(
                    train, test, features, target, is_variance
                )
                results.append(
                    {
                        "horizon": horizon,
                        "target": target_kind,
                        "model": model_name,
                        **metrics,
                    }
                )
    return pd.DataFrame(results)


# ============================================================================
# 5. MODEL COMPARISONS
# ============================================================================

def main():
    market, probability = load_data()
    model_data = build_model_data(market, probability)
    correlations = analyze_correlations(model_data)
    results = fit_all_models(model_data)
    correlations.to_csv(CORRELATIONS_PATH)
    results.to_csv(RESULTS_PATH, index=False)

    print("Stage 1 - data")
    print(f"SPY rows: {len(market)}")
    print(f"Probability rows: {len(probability)}")
    print(f"Usable modelling rows: {len(model_data)}")
    print("\nStage 3 - event feature / future return Spearman correlations")
    print(correlations.round(4).to_string())
    print("\nStage 5 - held-out model comparisons")
    print(results.round(6).to_string(index=False))
    print("\nHow to read these metrics:")
    print("- MAE and RMSE measure prediction error; lower is better.")
    print("- RMSE penalizes very bad predictions more heavily than MAE.")
    print("- R2 compares with a constant-average prediction; negative means worse.")
    print("- QLIKE is for variance forecasts; lower is better.")
    print("- Negative predictions are acceptable for returns, but not variance.")
    print("- Compare only the same target and horizon; 20-day results have few rows.")
    print("\nImplication:")
    print("- History-only was best for 1-day and 5-day return RMSE.")
    print("- Event-only was slightly best for 20-day return RMSE, but had only 15 test rows.")
    print("- History-plus-event did not beat history-only for variance.")
    print("- These results do not yet prove event features add forecasting value.")
    print("- More independent events, walk-forward tests, and smart-wallet features are needed.")
    print(f"\nSaved: {RESULTS_PATH}")
    print(f"Saved: {CORRELATIONS_PATH}")


if __name__ == "__main__":
    main()
