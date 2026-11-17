"""Meaningful boundary/coverage tests; no public API requests."""
import csv
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/polymarket"))
import wallet_cluster_collect as collection


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.config = {"snapshot_id": "test", "target_event_id": "101772", "seed": 42,
                       "target_wallets": 15, "selection_cutoff_utc": "2026-05-31T00:00:00Z",
                       "observation_start_utc": "2025-12-01T00:00:00Z", "max_pages": 2}
        self.wallet = "0x" + "1" * 40
        self.condition = "0x" + "2" * 64
        self.markets = {self.condition: {
            "market_id": "123", "event_id": "35090", "meeting_month": "2025-12", "rate_outcome": "No change",
            "tokens": {"987654321098765432109876543210": "Yes", "999": "No"},
            "decision_cutoff_utc": "2025-12-09T00:00:00+00:00", "market_end_date_utc": "2025-12-10T00:00:00+00:00"}}

    def record(self, **changes):
        result = {"proxy_wallet": self.wallet, "condition_id": self.condition,
                  "token_id": "987654321098765432109876543210", "side": "BUY", "size": "5.25",
                  "price": "0.2", "timestamp": int(collection.instant(self.config["observation_start_utc"]).timestamp()),
                  "transaction_hash": "0x" + "3" * 64}
        result.update(changes)
        return result

    def write_population(self, reverse=False):
        path = self.root / "datasets/polymarket/event_101772/wallet_discovery/wallet_summary_pre_cutoff.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        population = [{"wallet_address": "0x" + f"{i:040x}", "eligible": "True", "selection_cutoff_utc": self.config["selection_cutoff_utc"],
                       "markets_traded": 1 if i <= 20 else 4, "unique_transactions": 10 + i,
                       "active_days": 5 + i} for i in range(1, 61)]
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(population[0]))
            writer.writeheader()
            writer.writerows(list(reversed(population)) if reverse else population)

    def test_sampling_is_exact_reproducible_and_input_order_independent(self):
        self.write_population()
        first = collection.select_cohort(self.root, self.config)
        self.write_population(reverse=True)
        second = collection.select_cohort(self.root, self.config)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 15)
        self.assertEqual(len({r["wallet_address"] for r in first}), 15)
        self.assertEqual(sum(r["sampling_stratum"].startswith("focused") for r in first), 5)
        self.assertEqual(sum(r["sampling_stratum"].startswith("broad") for r in first), 10)

    def test_empty_exhausted_query_is_complete_zero_not_missing(self):
        response = {"data": [], "pagination": {"next_cursor": None}}
        with patch.object(collection, "_fetch_json", return_value=response):
            trades, coverage, rejected = collection._query_wallet(self.wallet, self.markets, self.config, self.root, time.monotonic() + 10)
        self.assertEqual(trades, [])
        self.assertEqual(rejected, [])
        self.assertTrue(coverage[0]["complete"])
        self.assertEqual(coverage[0]["participant_rows"], 0)

    def test_lower_bound_is_inclusive_and_large_token_id_preserved(self):
        response = {"data": [self.record()], "pagination": {"next_cursor": None}}
        with patch.object(collection, "_fetch_json", return_value=response):
            trades, coverage, _ = collection._query_wallet(self.wallet, self.markets, self.config, self.root, time.monotonic() + 10)
        self.assertTrue(coverage[0]["complete"])
        self.assertEqual(trades[0]["token_id"], self.record()["token_id"])
        self.assertEqual(trades[0]["signed_yes_shares"], "5.25")
        self.assertEqual(trades[0]["notional_usd"], "1.050")

    def test_upper_bound_and_wrong_wallet_are_not_accepted(self):
        for bad in [self.record(timestamp=int(collection.instant(self.config["selection_cutoff_utc"]).timestamp())),
                    self.record(proxy_wallet="0x" + "9" * 40)]:
            with tempfile.TemporaryDirectory() as cache:
                with patch.object(collection, "_fetch_json", return_value={"data": [bad], "pagination": {"next_cursor": None}}):
                    trades, coverage, _ = collection._query_wallet(self.wallet, self.markets, self.config, Path(cache), time.monotonic() + 10)
                self.assertEqual(trades, [])
                self.assertFalse(coverage[0]["complete"])

    def test_page_cap_marks_partial_data_incomplete_and_resume_uses_cache(self):
        config = dict(self.config, max_pages=1)
        response = {"data": [self.record()], "pagination": {"next_cursor": "second"}}
        with patch.object(collection, "_fetch_json", return_value=response):
            partial, coverage, _ = collection._query_wallet(self.wallet, self.markets, config, self.root, time.monotonic() + 10)
        self.assertEqual(len(partial), 1)
        self.assertFalse(coverage[0]["complete"])
        with patch.object(collection, "_fetch_json", return_value={"data": [], "pagination": {"next_cursor": None}}) as fetch:
            trades, coverage, _ = collection._query_wallet(self.wallet, self.markets, self.config, self.root, time.monotonic() + 10)
        self.assertEqual(len(trades), 1)
        self.assertTrue(coverage[0]["complete"])
        self.assertEqual(fetch.call_count, 1)

    def test_offline_cache_miss_is_incomplete_not_zero_history(self):
        config = dict(self.config, offline=True)
        with patch.object(collection, "_fetch_json") as fetch:
            trades, coverage, _ = collection._query_wallet(self.wallet, self.markets, config, self.root, time.monotonic() + 10)
        self.assertFalse(fetch.called)
        self.assertEqual(trades, [])
        self.assertFalse(coverage[0]["complete"])

    def test_target_metadata_rejects_wrong_market_and_changed_token_mapping(self):
        tokens = [{"condition_id": self.condition, "token_id": "123", "token_outcome": "YES"},
                  {"condition_id": self.condition, "token_id": "456", "token_outcome": "NO"}]
        metadata = {"id": "999", "conditionId": self.condition, "clobTokenIds": '["123", "456"]',
                    "outcomes": '["Yes", "No"]', "endDate": "2026-06-17T00:00:00Z"}
        with self.assertRaisesRegex(ValueError, "market mismatch"):
            collection._validate_target_metadata(metadata, "123", tokens)
        metadata["id"] = "123"
        collection._validate_target_metadata(metadata, "123", tokens)
        metadata["clobTokenIds"] = '["456", "123"]'
        with self.assertRaisesRegex(ValueError, "token mapping differs"):
            collection._validate_target_metadata(metadata, "123", tokens)


if __name__ == "__main__":
    unittest.main()
