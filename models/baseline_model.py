"""Leakage-safe baseline for forecasting SPY realized variance.

The script intentionally uses only the Python standard library and NumPy so it
can be run without the exploratory notebook's optional dependencies.
"""

import csv
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "datasets"
RESULTS_PATH = ROOT / "models" / "baseline_results.csv"
POSITIVE_FLOOR = 1e-8

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


def parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def load_market_rows():
    rows = []
    with (DATA_DIR / "index_daily.csv").open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row["ticker"] != "SPY" or not row["return_1d"]:
                continue
            rows.append(
                {
                    "date": parse_date(row["date"]),
                    "return": float(row["return_1d"]),
                }
            )
    return sorted(rows, key=lambda row: row["date"])


def load_event_features():
    by_date = defaultdict(list)
    with (DATA_DIR / "forward_probabilities.csv").open(
        newline="", encoding="utf-8-sig"
    ) as file:
        for row in csv.DictReader(file):
            move = OUTCOME_MOVE.get(row["outcome"])
            if move is None:
                continue
            by_date[(parse_date(row["date"]), int(row["horizon_month"]))].append(
                (float(row["market_probability"]), move)
            )

    features = {}
    for (date, horizon), observations in by_date.items():
        if not observations:
            continue
        # Use the nearest meeting available on that date, not the realized
        # outcome. Normalize within that meeting because some contracts are
        # absent from the source snapshot.
        if date not in features or horizon < features[date]["horizon"]:
            total = sum(probability for probability, _ in observations)
            if total <= 0:
                continue
            probabilities = [probability / total for probability, _ in observations]
            expected_move = sum(
                probability * move
                for probability, (_, move) in zip(probabilities, observations)
            )
            entropy = -sum(
                probability * math.log(max(probability, 1e-12))
                for probability in probabilities
            )
            features[date] = {
                "horizon": horizon,
                "expected_move": expected_move,
                "max_probability": max(probabilities),
                "entropy": entropy,
            }
    return features


def asof_event_features(dates, event_features):
    available = sorted(event_features)
    result = []
    pointer = 0
    latest = None
    for date in dates:
        while pointer < len(available) and available[pointer] <= date:
            latest = event_features[available[pointer]]
            pointer += 1
        result.append(latest)
    return result


def ols_fit_predict(train_x, train_y, test_x):
    coefficients, _, _, _ = np.linalg.lstsq(
        np.column_stack([np.ones(len(train_x)), train_x]), train_y, rcond=None
    )
    return np.column_stack([np.ones(len(test_x)), test_x]) @ coefficients


def qlike(actual, predicted):
    actual = np.maximum(actual, POSITIVE_FLOOR)
    predicted = np.maximum(predicted, POSITIVE_FLOOR)
    return float(np.mean(actual / predicted - np.log(actual / predicted) - 1.0))


def main():
    market = load_market_rows()
    events = load_event_features()
    dates = [row["date"] for row in market]
    returns = np.array([row["return"] for row in market], dtype=float)
    event_values = asof_event_features(dates, events)

    records = []
    for index in range(20, len(market) - 21):
        event = event_values[index]
        if event is None:
            continue
        past_rv20 = float(np.mean(returns[index - 20 : index] ** 2))
        for horizon in (1, 5, 20):
            if index + horizon > len(market):
                continue
            # The return at `index` is already known at this forecast origin.
            target = float(np.sum(returns[index + 1 : index + 1 + horizon] ** 2))
            records.append(
                {
                    "date": dates[index],
                    "horizon": horizon,
                    "past_rv20": past_rv20,
                    "expected_move": event["expected_move"],
                    "max_probability": event["max_probability"],
                    "entropy": event["entropy"],
                    "target_rv": target,
                }
            )

    output = []
    for horizon in (1, 5, 20):
        rows = [row for row in records if row["horizon"] == horizon]
        # Keep non-overlapping forecast origins. This avoids treating the same
        # future returns as independent observations for H > 1.
        rows = rows[::horizon]
        split = int(len(rows) * 0.7)
        train, test = rows[:split], rows[split:]
        y_train = np.array([row["target_rv"] for row in train])
        y_test = np.array([row["target_rv"] for row in test])
        baseline_x_train = np.array([[row["past_rv20"]] for row in train])
        baseline_x_test = np.array([[row["past_rv20"]] for row in test])
        augmented_columns = ("past_rv20", "expected_move", "max_probability", "entropy")
        augmented_x_train = np.array(
            [[row[column] for column in augmented_columns] for row in train]
        )
        augmented_x_test = np.array(
            [[row[column] for column in augmented_columns] for row in test]
        )
        predictions = {
            "recent_return_baseline": ols_fit_predict(
                baseline_x_train, y_train, baseline_x_test
            ),
            "event_augmented": ols_fit_predict(
                augmented_x_train, y_train, augmented_x_test
            ),
        }
        for model, predicted in predictions.items():
            output.append(
                {
                    "horizon": horizon,
                    "model": model,
                    "train_rows": len(train),
                    "test_rows": len(test),
                    "test_start": test[0]["date"].isoformat(),
                    "test_end": test[-1]["date"].isoformat(),
                    "mse": float(np.mean((y_test - predicted) ** 2)),
                    "qlike": qlike(y_test, predicted),
                    "negative_prediction_rate": float(np.mean(predicted < 0)),
                }
            )

    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output[0].keys())
        writer.writeheader()
        writer.writerows(output)
    for row in output:
        print(
            f"H={row['horizon']:>2} {row['model']:<24} "
            f"MSE={row['mse']:.8g} QLIKE={row['qlike']:.6g} "
            f"test={row['test_start']}..{row['test_end']}"
        )


if __name__ == "__main__":
    main()
