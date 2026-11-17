"""Independent raw-to-export checks catch internally consistent bad totals."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from run_wallet_cluster_pilot import validate
from wallet_cluster_daily import PANEL_COLUMNS, aggregate_four_direction
from wallet_cluster_features import FEATURE_NAMES


class PilotValidationTests(unittest.TestCase):
    def setUp(self):
        self.config = {"target_wallets": 1, "selection_cutoff_utc": "2026-05-31T00:00:00+00:00",
                       "observation_start_utc": "2025-12-01T00:00:00+00:00"}
        self.maps = [
            {"market_id": "historic", "decision_cutoff_utc": "2025-12-04T00:00:00+00:00"},
            {"market_id": "target", "decision_cutoff_utc": "2026-06-16T00:00:00+00:00"},
        ]
        self.features = pd.DataFrame([{**{name: 0 for name in FEATURE_NAMES},
            "wallet_address": "wallet", "coverage_complete": True,
            "participant_rows": 1, "gross_shares": 10}])
        self.membership = pd.DataFrame([{"wallet_address": "wallet", "cluster_id": "C0"}])
        self.history = [{"market_id": "historic", "wallet_address": "wallet",
            "timestamp_utc": "2025-12-02T12:00:00+00:00", "shares": "10", "notional_usd": "5"}]
        target = pd.DataFrame([{"wallet_address": "wallet", "market_id": "target",
            "timestamp_utc": "2026-05-31T12:00:00+00:00", "shares": "10",
            "notional_usd": "5", "side": "BUY", "token_outcome": "YES", "transaction_hash": "tx"}])
        stats = aggregate_four_direction(target)
        self.daily = {"signals": pd.DataFrame([{
            "asof_utc": "2026-06-01T00:00:00+00:00", "interval_start_utc": "2026-05-31T00:00:00+00:00",
            "event_id": "event", "market_id": "target", "cluster_id": "C0", "model_version": "m1",
            "decision_cutoff_utc": "2026-06-16T00:00:00+00:00", "coverage_complete": True,
            "forecast_input_allowed": True, **stats}]),
            "historical": pd.DataFrame(columns=PANEL_COLUMNS), "target_trades": target}

    def test_matching_raw_totals_pass(self):
        checks = validate(self.features, self.membership, self.daily, self.config, self.history, self.maps)
        self.assertTrue(all(checks.values()))

    def test_wrong_daily_total_fails_even_when_direction_identity_matches(self):
        bad = deepcopy(self.daily)
        bad["signals"].loc[0, ["buy_yes_shares", "gross_shares", "signed_yes_flow_shares"]] = 20
        with self.assertRaisesRegex(AssertionError, "raw_to_daily_reconciliation.*False"):
            validate(self.features, self.membership, bad, self.config, self.history, self.maps)

    def test_post_cutoff_history_cannot_be_included_in_feature_totals(self):
        history = self.history + [{**self.history[0], "timestamp_utc": "2025-12-04T00:00:00+00:00"}]
        # A raw audit export may retain the boundary record; a feature must not count it.
        checks = validate(self.features, self.membership, self.daily, self.config, history, self.maps)
        self.assertTrue(checks["raw_to_feature_reconciliation"])
        bad_features = self.features.copy()
        bad_features.loc[0, ["participant_rows", "gross_shares"]] = [2, 20]
        with self.assertRaisesRegex(AssertionError, "raw_to_feature_reconciliation.*False"):
            validate(bad_features, self.membership, self.daily, self.config, history, self.maps)


if __name__ == "__main__":
    unittest.main()
