"""Event-level walk-forward validation.

Each Federal Reserve event is held out as a complete test block. A model only
trains on events whose first observation occurred earlier in time. This avoids
claiming that repeated daily snapshots of one meeting are independent events.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forecast_models import (  # noqa: E402
    ALL_FEATURES,
    EVENT_FEATURES,
    HISTORY_FEATURES,
    HORIZONS,
    add_market_features,
    extract_event_features,
    load_data,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "models" / "event_walk_forward_results.csv"
REPORT_PATH = ROOT / "models" / "event_walk_forward_report.md"
MIN_TRAIN_EVENTS = 10


def build_data():
    market, probability = load_data()
    event = extract_event_features(probability)
    frame = add_market_features(market)
    data = pd.merge_asof(
        frame.sort_values("date"),
        event.sort_values("date"),
        on="date",
        direction="backward",
    ).dropna(subset=["expected_move", "event_id"])
    data["event_id"] = data["event_id"].astype(int)
    return data


def model_catalog():
    return {
        "ridge": lambda: make_pipeline(
            StandardScaler(), Ridge(alpha=1.0)
        ),
        "elastic_net": lambda: make_pipeline(
            StandardScaler(), ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=10000)
        ),
        "gradient_boosting": lambda: GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.03,
            max_depth=2,
            min_samples_leaf=8,
            random_state=42,
        ),
    }


def score(actual, prediction, is_variance):
    result = {
        "mae": mean_absolute_error(actual, prediction),
        "rmse": mean_squared_error(actual, prediction) ** 0.5,
        "r2": r2_score(actual, prediction) if len(actual) > 1 else np.nan,
        "negative_prediction_rate": float(np.mean(prediction < 0)),
        "test_rows": len(actual),
    }
    if is_variance:
        actual_floor = np.maximum(actual, 1e-8)
        prediction_floor = np.maximum(prediction, 1e-8)
        result["qlike"] = float(
            np.mean(
                actual_floor / prediction_floor
                - np.log(actual_floor / prediction_floor)
                - 1
            )
        )
    else:
        result["qlike"] = np.nan
    return result


def run(data):
    event_order = (
        data.groupby("event_id")["date"].min().sort_values().index.tolist()
    )
    rows = []
    for event_position, event_id in enumerate(event_order):
        if event_position < MIN_TRAIN_EVENTS:
            continue
        for horizon in HORIZONS:
            usable = data.dropna(
                subset=[
                    f"target_return_{horizon}d",
                    f"target_variance_{horizon}d",
                ]
            ).sort_values("date")
            # Keep complete event blocks, then space origins by H.
            usable = usable.iloc[::horizon]
            train = usable[usable["event_id"].isin(event_order[:event_position])]
            test = usable[usable["event_id"].eq(event_id)]
            if train.empty or test.empty:
                continue
            for target_name, is_variance in (
                ("return", False),
                ("variance", True),
            ):
                target = f"target_{target_name}_{horizon}d"
                feature_sets = {
                    "history_only": HISTORY_FEATURES,
                    "history_plus_event": ALL_FEATURES,
                }
                if target_name == "return":
                    feature_sets["event_only"] = EVENT_FEATURES
                for feature_set, features in feature_sets.items():
                    train_ready = train.dropna(subset=features + [target])
                    test_ready = test.dropna(subset=features + [target])
                    if len(train_ready) < 20 or test_ready.empty:
                        continue
                    for model_name, factory in model_catalog().items():
                        model = factory()
                        model.fit(train_ready[features], train_ready[target])
                        prediction = model.predict(test_ready[features])
                        metrics = score(
                            test_ready[target].to_numpy(),
                            prediction,
                            is_variance,
                        )
                        rows.append(
                            {
                                "test_event_id": event_id,
                                "test_event_position": event_position,
                                "test_start": test_ready["date"].min().date(),
                                "test_end": test_ready["date"].max().date(),
                                "horizon": horizon,
                                "target": target_name,
                                "feature_set": feature_set,
                                "model": model_name,
                                "train_events": event_position,
                                **metrics,
                            }
                        )
    return pd.DataFrame(rows)


def write_report(results):
    lines = [
        "# Event-level walk-forward validation",
        "",
        "Each complete Federal Reserve event is held out in chronological order.",
        "Training uses only earlier events. This is stricter than a daily random",
        "or single-date holdout because repeated snapshots of one meeting stay in",
        "the same event block.",
        "",
        f"- Minimum training events before a test: {MIN_TRAIN_EVENTS}",
        f"- Test event blocks evaluated: {results['test_event_id'].nunique()}",
        f"- Total scored fold/model rows: {len(results)}",
        "",
        "## Aggregate results",
        "",
    ]
    grouped = (
        results.groupby(["target", "horizon", "feature_set", "model"], as_index=False)
        .agg(
            folds=("test_event_id", "nunique"),
            test_rows=("test_rows", "sum"),
            mean_rmse=("rmse", "mean"),
            pooled_rmse=("rmse", lambda values: np.sqrt(np.mean(values**2))),
            mean_mae=("mae", "mean"),
            mean_r2=("r2", "mean"),
            mean_qlike=("qlike", "mean"),
        )
    )
    for (target, horizon), group in grouped.groupby(["target", "horizon"]):
        lines.append(f"### {target}, {horizon} trading day(s)")
        lines.append("")
        lines.append(
            group.sort_values("pooled_rmse")
            .round(6)
            .to_markdown(index=False)
        )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "History-plus-event is useful only if it beats history-only for the",
            "same target and horizon across event folds, not just in one fold.",
            "A result supported by many event folds is more credible than a result",
            "from a single 15-row holdout. This test still has a small number of",
            "independent events, so uncertainty should be reported.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return grouped


def main():
    data = build_data()
    results = run(data)
    if results.empty:
        raise RuntimeError("No event-level folds were available to score.")
    results.to_csv(RESULTS_PATH, index=False)
    grouped = write_report(results)
    print(grouped.sort_values(["target", "horizon", "pooled_rmse"]).round(6).to_string(index=False))
    print(f"\nSaved fold results to {RESULTS_PATH}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
