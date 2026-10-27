"""Model experiment playground.

This is a deliberately broad, reproducible comparison rather than the
production baseline. It logs every attempted model, feature set, horizon, and
target transformation to CSV and Markdown for later reporting.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

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
OUTPUT_DIR = ROOT / "models"
RESULTS_PATH = OUTPUT_DIR / "playground_experiment_results.csv"
DIAGNOSTICS_PATH = OUTPUT_DIR / "playground_diagnostics.csv"
REPORT_PATH = OUTPUT_DIR / "playground_experiment_report.md"
RANDOM_STATE = 42


def build_data():
    market, probability = load_data()
    event = extract_event_features(probability)
    frame = add_market_features(market)
    data = pd.merge_asof(
        frame.sort_values("date"),
        event.sort_values("date"),
        on="date",
        direction="backward",
    ).dropna(subset=["expected_move"])
    return data, probability


def model_catalog():
    """Return models with preprocessing appropriate to each estimator."""
    return {
        "ridge_alpha_0.01": make_pipeline(
            StandardScaler(), Ridge(alpha=0.01)
        ),
        "ridge_alpha_1": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "ridge_alpha_100": make_pipeline(
            StandardScaler(), Ridge(alpha=100.0)
        ),
        "elastic_net": make_pipeline(
            StandardScaler(), ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=10000)
        ),
        "svr_rbf": make_pipeline(
            StandardScaler(), SVR(C=1.0, epsilon=0.001, gamma="scale")
        ),
        "random_forest": RandomForestRegressor(
            n_estimators=300, min_samples_leaf=5, random_state=RANDOM_STATE, n_jobs=-1
        ),
        "extra_trees": ExtraTreesRegressor(
            n_estimators=300, min_samples_leaf=5, random_state=RANDOM_STATE, n_jobs=-1
        ),
        "gradient_boosting": GradientBoostingRegressor(
            n_estimators=100, learning_rate=0.03, max_depth=2,
            min_samples_leaf=8, random_state=RANDOM_STATE
        ),
        "hist_gradient_boosting": HistGradientBoostingRegressor(
            max_iter=100, learning_rate=0.03, max_leaf_nodes=7,
            l2_regularization=1.0, random_state=RANDOM_STATE
        ),
    }


def qlike(actual, predicted):
    actual = np.maximum(actual, 1e-8)
    predicted = np.maximum(predicted, 1e-8)
    return float(np.mean(actual / predicted - np.log(actual / predicted) - 1))


def fit_and_score(train, test, features, target, model, log_target, is_variance):
    train = train.dropna(subset=features + [target])
    test = test.dropna(subset=features + [target])
    y_train = train[target].to_numpy(dtype=float)
    y_test = test[target].to_numpy(dtype=float)
    if log_target:
        y_train_fit = np.log(y_train + 1e-8)
    else:
        y_train_fit = y_train
    model.fit(train[features], y_train_fit)
    prediction_fit = model.predict(test[features])
    prediction = np.exp(prediction_fit) - 1e-8 if log_target else prediction_fit
    return {
        "mae": mean_absolute_error(y_test, prediction),
        "rmse": mean_squared_error(y_test, prediction) ** 0.5,
        "r2": r2_score(y_test, prediction),
        "qlike": qlike(y_test, prediction) if is_variance else np.nan,
        "negative_prediction_rate": float(np.mean(prediction < 0)),
        "test_rows": len(test),
    }


def diagnostics(data, probability):
    chosen = (
        probability.sort_values(["date", "horizon_month"])
        .groupby("date", as_index=False)
        .first()
    )
    event_count = chosen["event_id"].nunique()
    correlation = data[ALL_FEATURES].corr().abs().copy()
    correlation_values = correlation.to_numpy(copy=True)
    np.fill_diagonal(correlation_values, np.nan)
    max_pair = np.nanmax(correlation_values)
    x = data[ALL_FEATURES].dropna().to_numpy(dtype=float)
    condition_number = float(np.linalg.cond(StandardScaler().fit_transform(x)))
    return {
        "market_rows": len(data),
        "unique_event_ids": event_count,
        "feature_count": len(ALL_FEATURES),
        "max_absolute_feature_correlation": float(max_pair),
        "feature_matrix_condition_number": condition_number,
    }


def run_experiments(data):
    feature_sets = {
        "history_only": HISTORY_FEATURES,
        "event_only": EVENT_FEATURES,
        "history_plus_event": ALL_FEATURES,
    }
    results = []
    for horizon in HORIZONS:
        usable = data.dropna(
            subset=[f"target_return_{horizon}d", f"target_variance_{horizon}d"]
        ).iloc[::horizon].reset_index(drop=True)
        split = int(len(usable) * 0.70)
        train, test = usable.iloc[:split], usable.iloc[split:]
        for target_name, is_variance in (
            ("return", False),
            ("variance", True),
        ):
            target = f"target_{target_name}_{horizon}d"
            for feature_name, features in feature_sets.items():
                # The event-only model is specifically requested for return.
                if is_variance and feature_name == "event_only":
                    continue
                for log_target in ([False, True] if is_variance else [False]):
                    for model_name, model in model_catalog().items():
                        metrics = fit_and_score(
                            train, test, features, target, model, log_target, is_variance
                        )
                        results.append(
                            {
                                "horizon": horizon,
                                "target": target_name,
                                "feature_set": feature_name,
                                "model": model_name,
                                "log_target": log_target,
                                "feature_count": len(features),
                                **metrics,
                            }
                        )
    return pd.DataFrame(results)


def write_report(results, diagnostic):
    report = [
        "# Playground experiment log",
        "",
        "This file records the broad model comparison run on the committed SPY and",
        "prediction-market data. The test period is chronological (last 30%), and",
        "multi-day origins are sampled every H trading days to avoid overlapping",
        "targets. These are exploratory results, not final evidence.",
        "",
        "## Data and diagnostics",
        "",
        f"- Market rows after cleaning: {diagnostic['market_rows']}",
        f"- Unique selected event IDs: {diagnostic['unique_event_ids']}",
        f"- Feature count in the full feature set: {diagnostic['feature_count']}",
        f"- Largest absolute feature correlation: {diagnostic['max_absolute_feature_correlation']:.4f}",
        f"- Feature matrix condition number: {diagnostic['feature_matrix_condition_number']:.2f}",
        "",
        "A high pairwise correlation or condition number indicates collinearity.",
        "The event rows are daily snapshots, so unique events are a better measure",
        "of independent information than the raw row count.",
        "",
        "## Best models by target and horizon",
        "",
    ]
    for (target, horizon), group in results.groupby(["target", "horizon"]):
        best = group.sort_values("rmse").iloc[0]
        report.append(
            f"- **{target}, {horizon}d:** `{best['model']}` + "
            f"`{best['feature_set']}` + log={best['log_target']} "
            f"(RMSE {best['rmse']:.8g}, R2 {best['r2']:.4f}, "
            f"test rows {int(best['test_rows'])})"
        )
    report.extend(["", "## History-plus-event versus history-only", ""])
    for (target, horizon), group in results.groupby(["target", "horizon"]):
        history = group[group["feature_set"].eq("history_only")].sort_values("rmse").iloc[0]
        combined = group[group["feature_set"].eq("history_plus_event")].sort_values("rmse").iloc[0]
        change = (combined["rmse"] / history["rmse"] - 1) * 100
        direction = "improved" if change < 0 else "worsened"
        report.append(
            f"- **{target}, {horizon}d:** best history-only `{history['model']}` "
            f"RMSE {history['rmse']:.8g}; best combined `{combined['model']}` "
            f"RMSE {combined['rmse']:.8g}; combined {direction} by {abs(change):.2f}%."
        )
    report.extend(
        [
            "",
            "## Interpretation rules",
            "",
            "- Compare history-plus-event with history-only at the same target and horizon.",
            "- A lower RMSE on one 15-row 20-day test is weak evidence.",
            "- If many complex models win only on the same small holdout, selection bias is possible.",
            "- If Ridge and tree models agree across horizons, the result is more credible.",
            "- If event features help only after log transformation, the original variance scale may be misspecified.",
            "- Better fit alone is not enough: event-blocked and walk-forward validation are still required.",
            "",
            "## Full run",
            "",
            f"Every attempted configuration is recorded in `{RESULTS_PATH.name}`.",
        ]
    )
    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")


def main():
    data, probability = build_data()
    diagnostic = diagnostics(data, probability)
    results = run_experiments(data)
    results.to_csv(RESULTS_PATH, index=False)
    pd.DataFrame([diagnostic]).to_csv(DIAGNOSTICS_PATH, index=False)
    write_report(results, diagnostic)
    print(results.sort_values(["target", "horizon", "rmse"]).groupby(
        ["target", "horizon"], as_index=False
    ).head(5).round(6).to_string(index=False))
    print(f"\nSaved {len(results)} experiment rows to {RESULTS_PATH}")
    print(f"Saved diagnostics to {DIAGNOSTICS_PATH}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
