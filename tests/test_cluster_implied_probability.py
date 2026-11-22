"""Cluster-implied probability: signs, windows, entities, weights, cutoffs."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from cluster_implied_probability import (  # noqa: E402
    ImpliedProbabilityConfig, implied_probabilities, prepare_memberships, tilt_probability,
)

ASOF = "2026-06-10T00:00:00+00:00"
PROBS = pd.DataFrame([
    {"asof_utc": ASOF, "event_id": "e", "market_id": "m1", "outcome": "no change", "market_probability": 0.6},
    {"asof_utc": ASOF, "event_id": "e", "market_id": "m2", "outcome": "25 bps decrease", "market_probability": 0.4},
])
CONFIG = ImpliedProbabilityConfig(window=pd.Timedelta(days=7), shrinkage_k=1.0, beta=2.0)


def trade(wallet, stamp, side="BUY", token="YES", shares=10, market="m1"):
    return {"wallet_address": wallet, "market_id": market, "timestamp_utc": stamp,
            "side": side, "token_outcome": token, "shares": str(shares)}


def members(*rows):
    return pd.DataFrame(rows)


def cell(panel, cluster="A", market="m1"):
    return panel.loc[panel.cluster_id.eq(cluster) & panel.market_id.eq(market)].iloc[0]


class ImpliedProbabilityTests(unittest.TestCase):
    def run_panel(self, trades, membership, **kwargs):
        return implied_probabilities(pd.DataFrame(trades), membership, PROBS, CONFIG, **kwargs)

    def test_inactive_cluster_equals_market(self):
        panel = self.run_panel([trade("w1", "2026-06-05T00:00:00+00:00")],
                               members({"wallet_address": "w1", "cluster_id": "A"},
                                       {"wallet_address": "w2", "cluster_id": "B"}))
        quiet = cell(panel, "B")
        self.assertEqual(quiet.active_entities, 0)
        self.assertEqual(quiet.cluster_probability, 0.6)
        self.assertEqual(cell(panel, "A", "m2").cluster_probability, 0.4)

    def test_four_directions(self):
        m = members({"wallet_address": "w1", "cluster_id": "A"})
        stamp = "2026-06-05T00:00:00+00:00"
        up = [trade("w1", stamp, "BUY", "YES"), trade("w1", stamp, "SELL", "NO")]
        down = [trade("w1", stamp, "SELL", "YES"), trade("w1", stamp, "BUY", "NO")]
        self.assertEqual(cell(self.run_panel(up, m)).tilt, 1.0)
        self.assertEqual(cell(self.run_panel(down, m)).tilt, -1.0)
        self.assertGreater(cell(self.run_panel(up, m)).cluster_probability, 0.6)
        self.assertLess(cell(self.run_panel(down, m)).cluster_probability, 0.6)

    def test_window_start_inclusive_asof_exclusive(self):
        m = members({"wallet_address": "w1", "cluster_id": "A"})
        start = self.run_panel([trade("w1", "2026-06-03T00:00:00+00:00")], m)
        at_asof = self.run_panel([trade("w1", ASOF)], m)
        before = self.run_panel([trade("w1", "2026-06-02T23:59:59+00:00")], m)
        self.assertEqual(cell(start).active_entities, 1)
        self.assertEqual(cell(at_asof).active_entities, 0)
        self.assertEqual(cell(before).active_entities, 0)

    def test_entity_netting_counts_owner_once(self):
        stamp = "2026-06-05T00:00:00+00:00"
        trades = [trade("w1", stamp, "BUY", "YES", 10), trade("w2", stamp, "SELL", "YES", 10)]
        same_owner = members({"wallet_address": "w1", "cluster_id": "A", "entity_id": "x"},
                             {"wallet_address": "w2", "cluster_id": "A", "entity_id": "x"})
        row = cell(self.run_panel(trades, same_owner))
        self.assertEqual(row.active_entities, 1)
        self.assertEqual(row.tilt, 0.0)

    def test_weights(self):
        stamp = "2026-06-05T00:00:00+00:00"
        trades = [trade("w1", stamp, "BUY", "YES"), trade("w2", stamp, "SELL", "YES")]
        weighted = members({"wallet_address": "w1", "cluster_id": "A", "weight": 3.0},
                           {"wallet_address": "w2", "cluster_id": "A", "weight": 1.0})
        self.assertAlmostEqual(cell(self.run_panel(trades, weighted)).tilt, 0.5)

    def test_decision_cutoff(self):
        m = members({"wallet_address": "w1", "cluster_id": "A"})
        trades = [trade("w1", "2026-06-08T00:00:00+00:00")]
        panel = self.run_panel(trades, m, decision_cutoffs={"m1": "2026-06-07T00:00:00+00:00"})
        self.assertTrue(panel.market_id.eq("m2").all())  # m1 as-of is after its cutoff
        panel = self.run_panel(trades, m, decision_cutoffs={"m1": "2026-06-11T00:00:00+00:00"})
        self.assertEqual(cell(panel).active_entities, 1)

    def test_membership_validation(self):
        with self.assertRaises(ValueError):
            prepare_memberships(members({"wallet_address": "w1", "cluster_id": "A"},
                                        {"wallet_address": "W1", "cluster_id": "B"}))
        with self.assertRaises(ValueError):
            prepare_memberships(members({"wallet_address": "w1", "cluster_id": "A", "entity_id": "x"},
                                        {"wallet_address": "w2", "cluster_id": "B", "entity_id": "x"}))
        table = prepare_memberships(members({"wallet_address": "w1", "cluster_id": None},
                                            {"wallet_address": "w2", "cluster_id": "B"}))
        self.assertEqual(table.wallet_address.tolist(), ["w2"])

    def test_tilt_bounded_and_monotone(self):
        tilts = np.linspace(-1, 1, 21)
        values = tilt_probability(np.full(21, 0.3), tilts, np.full(21, 5), k=3.0, beta=4.0)
        self.assertTrue(((values > 0) & (values < 1)).all())
        self.assertTrue(np.all(np.diff(values) > 0))
        self.assertAlmostEqual(values[10], 0.3)


if __name__ == "__main__":
    unittest.main()
