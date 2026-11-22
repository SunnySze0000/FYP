"""Wallet pipeline stages: trade normalization, same-owner links, rules, clustering."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from wallet_pipeline.behaviour import ClusterConfig, entity_features, fit, prepare_matrix  # noqa: E402
from wallet_pipeline.owners import OwnerConfig, assign_entities, co_trading_pairs, linked_pairs  # noqa: E402
from wallet_pipeline.rules import RuleConfig, apply_rules, rule_counts  # noqa: E402
from wallet_pipeline.trades import normalize  # noqa: E402


def row(wallet, stamp, tx, side="BUY", token="YES", shares="10", market="m1", price="0.5"):
    return {"timestamp_utc": stamp, "event_id": "e", "market_id": market, "rate_outcome": "no change",
            "token_outcome": token, "wallet_address": wallet, "side": side, "shares": shares, "price": price,
            "notional_usd": str(float(shares) * float(price)), "transaction_hash": tx, "same_fingerprint_count": "1"}


def sniper_days(days=4, per_day=2, lag=1, same_tx=False):
    rows = []
    for d in range(days):
        for k in range(per_day):
            base = pd.Timestamp("2026-05-01T10:00:00Z") + pd.Timedelta(days=d, minutes=10 * k)
            tx_a = f"tx{d}_{k}"
            rows.append(row("a", base.isoformat(), tx_a))
            rows.append(row("b", (base + pd.Timedelta(seconds=lag)).isoformat(), tx_a if same_tx else tx_a + "b"))
    return rows


class TradeTests(unittest.TestCase):
    def test_direction_seconds_and_taker(self):
        data = normalize(pd.DataFrame([
            row("t", "2026-05-01T00:00:01+00:00", "x", "BUY", "YES", "30"),
            row("m1", "2026-05-01T00:00:01+00:00", "x", "SELL", "YES", "10"),
            row("m2", "2026-05-01T00:00:01+00:00", "x", "BUY", "NO", "20"),
            row("p", "2026-05-01T00:00:02+00:00", "y", "SELL", "NO", "5"),
            row("q", "2026-05-01T00:00:02+00:00", "y", "BUY", "NO", "5"),
        ]))
        self.assertEqual(data["direction"].tolist(), [1, -1, -1, 1, -1])
        self.assertEqual(data["second"].iloc[0], 1777593601)          # resolution-safe epoch seconds
        self.assertEqual(data["taker_role"].iloc[:3].tolist(), [1.0, 0.0, 0.0])
        self.assertTrue(data["taker_role"].iloc[3:].isna().all())    # 2-wallet fill: unknown

    def test_cutoff_is_exclusive(self):
        data = normalize(pd.DataFrame([row("a", "2026-05-31T00:00:00+00:00", "x"),
                                       row("a", "2026-05-30T23:59:59+00:00", "y")]), "2026-05-31T00:00:00Z")
        self.assertEqual(len(data), 1)


class OwnerTests(unittest.TestCase):
    cfg = OwnerConfig(min_co_moments=5, min_co_days=3, min_jaccard=0.2)

    def entities(self, rows, cfg=None):
        cfg = cfg or self.cfg
        data = normalize(pd.DataFrame(rows))
        return assign_entities(data["wallet_address"].unique(), linked_pairs(co_trading_pairs(data, cfg), cfg), cfg)

    def test_co_timed_wallets_merge(self):
        table = self.entities(sniper_days())
        self.assertEqual(table["entity_id"].nunique(), 1)
        self.assertTrue(table["owner_status"].eq("merged").all())

    def test_same_transaction_is_counterparty_not_owner(self):
        self.assertEqual(self.entities(sniper_days(same_tx=True))["entity_id"].nunique(), 2)

    def test_needs_several_days_and_close_timing(self):
        self.assertEqual(self.entities(sniper_days(days=2, per_day=4))["entity_id"].nunique(), 2)
        self.assertEqual(self.entities(sniper_days(lag=5))["entity_id"].nunique(), 2)

    def test_hub_does_not_chain_small_wallets(self):
        rows = sniper_days()
        # a busy bot "h" trades beside a at every moment but also 200 other times.
        for r in [r for r in rows if r["wallet_address"] == "a"]:
            rows.append(row("h", r["timestamp_utc"], "h" + r["transaction_hash"]))
        for i in range(200):
            rows.append(row("h", (pd.Timestamp("2026-04-01T00:00:00Z") + pd.Timedelta(minutes=i)).isoformat(), f"hx{i}"))
        table = self.entities(rows).set_index("wallet_address")
        self.assertEqual(table.loc["a", "entity_id"], table.loc["b", "entity_id"])
        self.assertNotEqual(table.loc["h", "entity_id"], table.loc["a", "entity_id"])

    def test_oversized_component_not_merged(self):
        cfg = OwnerConfig(max_component_size=1)
        table = self.entities(sniper_days(), cfg)
        self.assertTrue(table["owner_status"].eq("oversized_component_not_merged").all())
        self.assertEqual(table["entity_id"].nunique(), 2)


class RuleAndClusterTests(unittest.TestCase):
    def test_entity_features_and_rules(self):
        data = normalize(pd.DataFrame(sniper_days(days=4, per_day=3)))
        entities = pd.DataFrame({"wallet_address": ["a", "b"], "entity_id": ["E", "E"]})
        features = entity_features(data, entities, "2026-05-31T00:00:00Z")
        self.assertEqual(len(features), 1)
        self.assertEqual(features["trades"].iloc[0], 24)
        self.assertEqual(features["active_days"].iloc[0], 4)
        self.assertAlmostEqual(features["net_direction_consistency"].iloc[0], 1.0)
        ruled = apply_rules(features, RuleConfig(min_total_notional_usd=1000))
        self.assertFalse(ruled["eligible"].iloc[0])
        self.assertEqual(ruled["rule_failures"].iloc[0], "below_min_total_notional")
        self.assertEqual(rule_counts(ruled)["below_min_total_notional"], 1)

    def test_fit_recovers_separated_groups(self):
        rng = np.random.default_rng(1)
        n = 60
        frame = pd.DataFrame({"x": np.r_[rng.normal(0, .1, n), rng.normal(5, .1, n)],
                              "y": np.r_[rng.normal(0, .1, n), rng.normal(5, .1, n)],
                              "taker_fraction": np.r_[np.full(n, np.nan), rng.uniform(size=n)]})
        prepared, retained, removed = prepare_matrix(frame, ["x", "y", "taker_fraction"])
        self.assertFalse(prepared["taker_fraction"].isna().any())
        _, labels, distances, diagnostics, summary = fit(prepared, ["x", "y"], ClusterConfig(k_values=(2, 3, 4)))
        self.assertEqual(summary["selected_k"], 2)
        self.assertEqual(len(set(labels[:n])), 1)
        self.assertNotEqual(labels[0], labels[-1])
        self.assertEqual(len(distances), 2 * n)


if __name__ == "__main__":
    unittest.main()
