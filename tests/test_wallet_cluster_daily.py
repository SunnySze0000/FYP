"""Boundary and accounting checks for frozen cluster daily signals."""
import csv
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from wallet_cluster_daily import aggregate_four_direction, _panel, build_daily

CONFIG = {
    "snapshot_id": "test_snapshot", "selection_cutoff_utc": "2026-05-31T00:00:00+00:00",
    "observation_start_utc": "2026-05-01T00:00:00+00:00",
    "history_event_ids": ["old"], "target_event_id": "target",
}
MEMBERS = pd.DataFrame([
    {"wallet_address": "wallet_a", "cluster_id": "0", "model_version": "m1"},
    {"wallet_address": "wallet_b", "cluster_id": "0", "model_version": "m1"},
])
MAPS = {"market": {"event_id": "target", "market_id": "market", "condition_id": "cond",
                   "rate_outcome": "No change", "decision_cutoff_utc": "2026-06-02T12:00:00+00:00"}}


def trade(stamp, side="BUY", token="YES", shares="10", wallet="wallet_a", tx="tx1"):
    return {"wallet_address": wallet, "market_id": "market", "event_id": "target",
            "condition_id": "cond", "timestamp_utc": stamp, "side": side,
            "token_outcome": token, "shares": shares, "notional_usd": str(float(shares) * .5),
            "transaction_hash": tx, "source_page": "1", "source_row": "1"}


class FourDirectionTests(unittest.TestCase):
    def test_four_actions_and_shared_transaction(self):
        rows = pd.DataFrame([
            trade("2026-05-31T10:00:00+00:00", "BUY", "YES", "10"),
            trade("2026-05-31T10:00:00+00:00", "SELL", "YES", "3"),
            trade("2026-05-31T10:00:00+00:00", "BUY", "NO", "2", "wallet_b"),
            trade("2026-05-31T10:00:00+00:00", "SELL", "NO", "5", "wallet_b"),
        ])
        out = aggregate_four_direction(rows)
        self.assertEqual(out["signed_yes_flow_shares"], 10)
        self.assertEqual(out["gross_shares"], 20)
        self.assertEqual(out["participant_rows"], 4)
        self.assertEqual(out["unique_transactions"], 1)
        self.assertEqual(out["active_wallet_count"], 2)
        self.assertAlmostEqual(out["aggregate_directional_imbalance"], .5)
        self.assertAlmostEqual(out["equal_weight_directional_imbalance"], ((7 / 13) + (3 / 7)) / 2)

    def test_no_activity_keeps_undefined_ratios_missing(self):
        out = aggregate_four_direction(pd.DataFrame())
        self.assertTrue(out["no_activity"])
        self.assertEqual(out["gross_shares"], 0)
        self.assertTrue(np.isnan(out["aggregate_directional_imbalance"]))
        self.assertTrue(np.isnan(out["equal_weight_directional_imbalance"]))

    def test_zero_notional_does_not_hide_share_flow(self):
        row = trade("2026-05-31T10:00:00+00:00")
        row["notional_usd"] = "0"
        out = aggregate_four_direction(pd.DataFrame([row]))
        self.assertEqual(out["aggregate_directional_imbalance"], 1)
        self.assertTrue(np.isnan(out["largest_wallet_notional_fraction"]))


class DailyBoundaries(unittest.TestCase):
    def test_midnight_exclusive_upper_and_inclusive_lower(self):
        rows = pd.DataFrame([
            trade("2026-05-30T23:59:59+00:00", shares="1", tx="before"),
            trade("2026-05-31T00:00:00+00:00", shares="2", tx="at"),
            trade("2026-05-31T23:59:59+00:00", shares="3", tx="last"),
            trade("2026-06-01T00:00:00+00:00", shares="4", tx="next"),
        ])
        coverage = pd.DataFrame([{"wallet_address": a, "market_id": "market", "complete": True}
                                 for a in MEMBERS["wallet_address"]])
        panel = _panel(rows, MEMBERS, MAPS, {"target"}, CONFIG, True, coverage)
        self.assertEqual(panel["gross_shares"].tolist(), [1, 5, 4])
        self.assertTrue(panel["forecast_input_allowed"].all())
        self.assertEqual(panel["asof_utc"].max(), "2026-06-02T00:00:00+00:00")

    def test_missing_wallet_coverage_does_not_create_zero(self):
        coverage = pd.DataFrame([{"wallet_address": "wallet_a", "market_id": "market", "complete": True}])
        panel = _panel(pd.DataFrame(), MEMBERS, MAPS, {"target"}, CONFIG, True, coverage)
        self.assertTrue(panel["gross_shares"].isna().all())
        self.assertTrue(panel["no_activity"].isna().all())
        self.assertFalse(panel["coverage_complete"].any())
        self.assertFalse(panel["forecast_input_allowed"].any())
        self.assertEqual(set(panel["complete_wallet_count"]), {1})

    def test_history_never_forecast_input_and_stops_at_cutoff(self):
        mapping = {"market": {**MAPS["market"], "event_id": "old",
                              "decision_cutoff_utc": "2026-05-04T12:00:00+00:00"}}
        rows = pd.DataFrame([
            {**trade("2026-05-03T23:59:59+00:00"), "event_id": "old"},
            {**trade("2026-05-04T12:00:00+00:00", shares="999"), "event_id": "old"},
        ])
        panel = _panel(rows, MEMBERS, mapping, {"old"}, CONFIG, False)
        self.assertFalse(panel["forecast_input_allowed"].any())
        self.assertEqual(panel["asof_utc"].max(), "2026-05-04T00:00:00+00:00")
        self.assertEqual(panel["gross_shares"].sum(), 10)

    def test_target_export_and_manifest_reconciliation(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            base = root / "datasets" / "polymarket"
            event = base / "event_target"
            source = base / "market_market"
            event.mkdir(parents=True)
            source.mkdir()
            row = trade("2026-05-31T10:00:00+00:00")
            with gzip.open(source / "wallet_trades.csv.gz", "wt", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            manifest = {"exhausted_api_cursor": True, "clean_rows": 1, "rejected_rows": 0}
            (source / "manifest.json").write_text(json.dumps(manifest))
            inventory = {"market_id": "market", "market_directory": "../market_market",
                         "exhausted_api_cursor": "True", "participant_rows": "1", "rejected_rows": "0"}
            with (event / "market_inventory.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(inventory))
                writer.writeheader()
                writer.writerow(inventory)
            cohort = [{"wallet_address": address} for address in MEMBERS["wallet_address"]]
            output = build_daily(cohort, MEMBERS, [], list(MAPS.values()), root, CONFIG)
            self.assertTrue(output["coverage"]["complete"].all())
            self.assertEqual(output["signals"]["gross_shares"].sum(), 10)
            self.assertEqual(output["report"]["target_trade_rows"], 1)
            manifest["clean_rows"] = 2
            (source / "manifest.json").write_text(json.dumps(manifest))
            bad = build_daily(cohort, MEMBERS, [], list(MAPS.values()), root, CONFIG)
            self.assertTrue(bad["signals"]["gross_shares"].isna().all())
            self.assertFalse(bad["signals"]["forecast_input_allowed"].any())


if __name__ == "__main__":
    unittest.main()
