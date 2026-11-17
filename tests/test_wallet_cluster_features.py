"""Boundary and semantic checks for the wallet behavioural pilot."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from wallet_cluster_features import CLUSTER_FEATURES, FEATURE_NAMES, build_features, fit_clusters


CONFIG = {
    "snapshot_id": "test_fed_snapshot", "selection_cutoff_utc": "2026-05-31T00:00:00Z",
    "observation_start_utc": "2025-12-01T00:00:00Z", "history_event_ids": ["e1", "e2"], "seed": 42,
}
MARKETS = [
    {"event_id": "e1", "market_id": "m1", "decision_cutoff_utc": "2026-01-15T00:00:00Z"},
    {"event_id": "e1", "market_id": "m1b", "decision_cutoff_utc": "2026-01-15T00:00:00Z"},
    {"event_id": "e2", "market_id": "m2", "decision_cutoff_utc": "2026-04-15T00:00:00Z"},
    {"event_id": "e2", "market_id": "m2b", "decision_cutoff_utc": "2026-04-15T00:00:00Z"},
]


def trade(index, *, side="BUY", token="YES", shares=10, timestamp=None, event=None, market=None,
          tx=None, fingerprint=None):
    event = event or ("e1" if index < 6 else "e2")
    market = market or ("m1" if event == "e1" else "m2")
    timestamp = timestamp or (f"2026-01-{index + 1:02d}T12:00:00Z" if event == "e1"
                              else f"2026-04-{index - 5:02d}T12:00:00Z")
    return {"wallet_address": "0xabc", "event_id": event, "market_id": market,
            "timestamp_utc": timestamp, "transaction_hash": tx or f"tx{index}",
            "token_id": market + token, "token_outcome": token, "side": side,
            "shares": str(shares), "price": ".5", "notional_usd": str(shares * .5),
            "record_fingerprint": fingerprint or f"fingerprint{index}", "chain_verification": "not_checked"}


def coverage(complete=True):
    return [{"wallet_address": "0xabc", "event_id": event, "complete": complete} for event in ["e1", "e2"]]


def features(trades, cov=None):
    return build_features([{"wallet_address": "0xabc"}], trades, coverage() if cov is None else cov,
                          MARKETS, CONFIG).iloc[0]


class FeatureBoundaryTests(unittest.TestCase):
    def test_thirty_feature_contract(self):
        self.assertEqual(len(FEATURE_NAMES), 30)
        self.assertEqual(len(set(FEATURE_NAMES)), 30)
        self.assertEqual(len(CLUSTER_FEATURES), 8)

    def test_event_and_global_cutoffs_are_strict(self):
        rows = [trade(index) for index in range(12)]
        rows += [trade(100, event="e1", timestamp="2026-01-15T00:00:00Z"),
                 trade(101, event="e2", timestamp="2026-05-31T00:00:00Z"),
                 trade(102, event="e1", timestamp="2025-11-30T23:59:59Z")]
        result = features(rows)
        self.assertEqual(result.participant_rows, 12)
        self.assertTrue(result.eligible)
        self.assertLess(pd.Timestamp(result.last_feature_trade_utc), pd.Timestamp(CONFIG["selection_cutoff_utc"]))

    def test_later_duplicate_does_not_change_quality(self):
        rows = [trade(index) for index in range(12)]
        rows += [trade(100, event="e1", timestamp="2026-01-15T00:00:00Z", fingerprint="fingerprint0")]
        result = features(rows)
        self.assertEqual(result.duplicate_candidate_fraction, 0)
        self.assertTrue(result.eligible)

    def test_same_transaction_multiple_records_retains_shares(self):
        result = features([trade(0, shares=10, tx="same"), trade(1, shares=20, tx="same")])
        self.assertEqual(result.participant_rows, 2)
        self.assertEqual(result.unique_transactions, 1)
        self.assertEqual(result.gross_shares, 30)

    def test_four_directions_and_netting(self):
        result = features([trade(0, side="BUY", token="YES", shares=10),
                           trade(1, side="SELL", token="YES", shares=4),
                           trade(2, side="BUY", token="NO", shares=3),
                           trade(3, side="SELL", token="NO", shares=2)])
        self.assertEqual(result.buy_yes_shares, 10)
        self.assertEqual(result.sell_yes_shares, 4)
        self.assertEqual(result.buy_no_shares, 3)
        self.assertEqual(result.sell_no_shares, 2)
        self.assertAlmostEqual(result.absolute_market_netting_ratio, 5 / 19)
        self.assertEqual(result.two_sided_token_fraction, 1)

    def test_incomplete_collection_is_not_zero_activity(self):
        result = features([trade(index) for index in range(12)], cov=coverage(False))
        self.assertFalse(result.eligible)
        self.assertTrue(np.isnan(result.participant_rows))
        self.assertEqual(result.observed_participant_rows, 12)
        self.assertIn("incomplete_collection", result.eligibility_status)
        self.assertEqual(result.complete_events, 0)

    def test_zero_notional_ratios_remain_missing(self):
        rows = [trade(index) for index in range(12)]
        for row in rows:
            row.update(price="0", notional_usd="0")
        result = features(rows)
        self.assertTrue(np.isnan(result.median_event_top_market_fraction))
        self.assertFalse(result.eligible)

    def test_future_label_columns_do_not_enter_features(self):
        rows = [trade(index) for index in range(12)]
        baseline = features(rows)
        for row in rows:
            row.update(final_outcome="1", future_return="123456", lifetime_volume="999999")
        result = features(rows)
        pd.testing.assert_series_equal(baseline, result)


class FrozenModelTests(unittest.TestCase):
    def test_no_fit_removes_only_stale_generated_model_artifacts(self):
        data = build_features([{"wallet_address": "0xabc"}], [], coverage(False), MARKETS, CONFIG)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "charts").mkdir()
            stale = [out / "pipeline.joblib"] + [out / "charts" / name for name in (
                "cluster_feature_profiles.png", "cluster_selection.png", "silhouette.png", "wallet_pca.png")]
            for artifact in stale:
                artifact.write_bytes(b"previous run")
            unrelated = out / "charts" / "team_notes.txt"
            unrelated.write_text("preserve")
            result = fit_clusters(data, CONFIG, out)
            self.assertEqual(result["report"]["status"], "not_fitted")
            self.assertTrue(all(not artifact.exists() for artifact in stale))
            self.assertEqual(unrelated.read_text(), "preserve")

    def test_empty_fit_provides_unassigned_membership(self):
        data = build_features([{"wallet_address": "0xabc"}], [], coverage(False), MARKETS, CONFIG)
        with tempfile.TemporaryDirectory() as directory:
            result = fit_clusters(data, CONFIG, Path(directory))
        self.assertEqual(result["report"]["status"], "not_fitted")
        self.assertEqual(result["memberships"].iloc[0].cluster_id, "")

    def test_frozen_pipeline_roundtrip_and_determinism(self):
        import joblib
        rng = np.random.default_rng(42)
        data = []
        for index in range(60):
            group = index // 30
            values = {name: float(1 + group * 8 + rng.uniform(.1, .4)) for name in FEATURE_NAMES}
            for name in ["median_event_top_market_fraction", "two_sided_token_fraction", "busiest_day_transaction_fraction"]:
                values[name] = float(.1 + group * .7 + rng.uniform(.01, .04))
            data.append({"snapshot_id": CONFIG["snapshot_id"], "wallet_address": f"wallet{index:03d}",
                         "eligible": True, "eligibility_status": "eligible", **values})
        frame = pd.DataFrame(data)
        with tempfile.TemporaryDirectory() as directory:
            first = fit_clusters(frame, CONFIG, Path(directory) / "first")
            second = fit_clusters(frame, CONFIG, Path(directory) / "second")
            model = joblib.load(Path(directory) / "first" / "pipeline.joblib")
            predictions = model.predict(frame)
            expected = [f"C{label}" for label in predictions]
            self.assertEqual(first["memberships"].cluster_id.tolist(), expected)
            pd.testing.assert_frame_equal(first["memberships"], second["memberships"])
            self.assertEqual(first["report"]["selected_k"], 2)
            self.assertEqual(len(first["profiles"]), 2 * 30)
            self.assertEqual(len(list((Path(directory) / "first" / "charts").glob("*.png"))), 4)


if __name__ == "__main__":
    unittest.main()
