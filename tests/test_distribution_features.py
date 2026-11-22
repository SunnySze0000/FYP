"""Distribution summaries and market comparisons; outcome vocabulary."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models"))
from distribution_features import compare, summarize  # noqa: E402
from outcomes import OUTCOME_MOVE, normalize_outcome, outcome_move  # noqa: E402


def dist(probabilities, reference=None):
    moves = [-50.0, -25.0, 0.0, 25.0]
    rows = pd.DataFrame({"g": 1, "move": moves, "probability": probabilities})
    if reference is not None:
        rows["market"] = reference
    return rows


class SummaryTests(unittest.TestCase):
    def test_point_mass(self):
        row = summarize(dist([0, 0, 1, 0]), ["g"]).iloc[0]
        self.assertEqual(row.expected_move, 0)
        self.assertEqual(row.move_std, 0)
        self.assertAlmostEqual(row.entropy, 0)
        self.assertEqual(row.max_probability, 1)
        self.assertEqual(row.probability_no_change, 1)

    def test_uniform_and_renormalization(self):
        row = summarize(dist([2, 2, 2, 2]), ["g"]).iloc[0]
        self.assertAlmostEqual(row.entropy_normalized, 1.0)
        self.assertAlmostEqual(row.expected_move, -12.5)
        self.assertAlmostEqual(row.tail_probability, 0.25)
        self.assertAlmostEqual(row.probability_decrease + row.probability_increase + row.probability_no_change, 1)

    def test_compare_identical_is_zero(self):
        p = [0.1, 0.3, 0.5, 0.1]
        row = compare(dist(p, p), ["g"], reference="market").iloc[0]
        for name in ("expected_move_gap", "move_std_gap", "tail_probability_gap", "kl_from_market", "total_variation"):
            self.assertAlmostEqual(row[name], 0.0)

    def test_compare_direction(self):
        row = compare(dist([0.0, 0.1, 0.5, 0.4], [0.1, 0.3, 0.5, 0.1]), ["g"], reference="market").iloc[0]
        self.assertGreater(row.expected_move_gap, 0)      # cluster more hawkish
        self.assertLess(row.tail_probability_gap, 0)      # less 50 bp cut mass
        self.assertGreater(row.kl_from_market, 0)
        self.assertTrue(0 < row.total_variation <= 1)


class OutcomeTests(unittest.TestCase):
    def test_normalization_and_open_buckets(self):
        self.assertEqual(normalize_outcome("  No   Change "), "no change")
        self.assertEqual(OUTCOME_MOVE["25+ bps increase"], 25.0)
        moves = outcome_move(pd.Series(["No change", "25+ bps increase", "other"]))
        self.assertEqual(moves.iloc[0], 0.0)
        self.assertEqual(moves.iloc[1], 25.0)
        self.assertTrue(np.isnan(moves.iloc[2]))


if __name__ == "__main__":
    unittest.main()
