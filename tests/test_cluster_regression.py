"""N x M feature shaping and the walk-forward path on synthetic events."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models"))
from cluster_regression import cluster_features, evaluate  # noqa: E402
from forecast_models import HISTORY_FEATURES, EVENT_FEATURES, HORIZONS  # noqa: E402


def panel(days=3, clusters=("C0", "C1")):
    rows = []
    outcomes = [("25 bps decrease", -25.0, 0.3), ("no change", 0.0, 0.6), ("25 bps increase", 25.0, 0.1)]
    for d in range(days):
        for c in clusters:
            for i, (name, move, p) in enumerate(outcomes):
                rows.append(dict(asof_utc=pd.Timestamp("2026-06-01", tz="UTC") + pd.Timedelta(days=d),
                                 event_id="e", market_id=f"m{i}", outcome=name, move=move,
                                 cluster_id=c, market_probability=p,
                                 cluster_probability=p + (0.05 if c == "C0" and i == 2 else 0.0),
                                 active_entities=1))
    return pd.DataFrame(rows)


class FeatureShapeTests(unittest.TestCase):
    def test_summary_is_n_by_m(self):
        wide = cluster_features(panel(), "summary")
        model = [c for c in wide.columns if "__" in c and not c.endswith("active_entities")]
        self.assertEqual(len(wide), 3)
        self.assertEqual(len(model), 2 * 4)
        self.assertGreater(wide["C0__expected_move_gap"].iloc[0], 0)
        self.assertAlmostEqual(wide["C1__kl_from_market"].iloc[0], 0)

    def test_other_modes(self):
        self.assertEqual(sum("p_gap_" in c for c in cluster_features(panel(), "per_outcome").columns), 2 * 3)
        self.assertIn("C1__entropy_normalized", cluster_features(panel(), "levels").columns)
        with self.assertRaises(ValueError):
            cluster_features(panel(), "bad")


class EvaluateTests(unittest.TestCase):
    def synthetic(self, events):
        rng = np.random.default_rng(0)
        dates = pd.bdate_range("2025-01-01", periods=events * 30)
        data = pd.DataFrame({"date": dates, "event_id": np.repeat(np.arange(events), 30)})
        for column in HISTORY_FEATURES + EVENT_FEATURES + ["C0__x", "C1__x"]:
            data[column] = rng.normal(size=len(data))
        for h in HORIZONS:
            data[f"target_return_{h}d"] = 0.01 * data["C0__x"] + rng.normal(scale=0.001, size=len(data))
            data[f"target_variance_{h}d"] = rng.uniform(1e-5, 1e-4, size=len(data))
        return data

    def test_insufficient_events(self):
        results, status = evaluate(self.synthetic(1), ["C0__x", "C1__x"])
        self.assertTrue(results.empty)
        self.assertTrue(status.startswith("insufficient_events"))

    def test_walk_forward_includes_cluster_set(self):
        results, status = evaluate(self.synthetic(4), ["C0__x", "C1__x", "C0__active_entities"])
        self.assertEqual(status, "evaluated")
        self.assertIn("history_plus_event_plus_cluster", set(results.feature_set))
        ret = results.loc[results.target.eq("return") & results.horizon.eq(1) & results.model.eq("ridge")]
        rmse = ret.groupby("feature_set").rmse.mean()
        self.assertLess(rmse["history_plus_event_plus_cluster"], rmse["history_plus_event"])


if __name__ == "__main__":
    unittest.main()
