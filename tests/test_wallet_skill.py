"""Past-only flow-alignment skill scores."""
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "polymarket"))
from wallet_skill import filter_by_skill, meeting_alignment, skill_scores, skill_weights  # noqa: E402

OUTCOMES = pd.DataFrame([
    {"event_id": "e1", "market_id": "m1", "decision_cutoff_utc": "2026-01-10T00:00:00+00:00",
     "cutoff_probability": 0.8, "final_outcome": 1},
    {"event_id": "e2", "market_id": "m2", "decision_cutoff_utc": "2026-03-10T00:00:00+00:00",
     "cutoff_probability": 0.8, "final_outcome": 1},
])


def trade(market, stamp, token="YES", wallet="w1"):
    return {"wallet_address": wallet, "market_id": market, "timestamp_utc": stamp,
            "side": "BUY", "token_outcome": token, "shares": "100"}


class SkillTests(unittest.TestCase):
    def test_readme_example_and_window(self):
        trades = pd.DataFrame([trade("m1", "2026-01-09T00:00:00+00:00"),
                               trade("m1", "2025-12-01T00:00:00+00:00")])  # outside 7-day window
        align = meeting_alignment(trades, OUTCOMES)
        self.assertAlmostEqual(align.alignment.iloc[0], 0.2)
        no = meeting_alignment(pd.DataFrame([trade("m1", "2026-01-09T00:00:00+00:00", "NO")]), OUTCOMES)
        self.assertAlmostEqual(no.alignment.iloc[0], -0.2)

    def test_as_of_excludes_unresolved_and_shrinks(self):
        trades = pd.DataFrame([trade("m1", "2026-01-09T00:00:00+00:00"),
                               trade("m2", "2026-03-09T00:00:00+00:00")])
        align = meeting_alignment(trades, OUTCOMES)
        early = skill_scores(align, "2026-02-01", prior_meetings=2).iloc[0]
        late = skill_scores(align, "2026-04-01", prior_meetings=2).iloc[0]
        self.assertEqual(early.meetings_scored, 1)
        self.assertAlmostEqual(early.skill, 0.2 / 3)
        self.assertEqual(late.meetings_scored, 2)
        self.assertAlmostEqual(late.skill, 0.4 / 4)

    def test_filter_and_weights(self):
        scores = pd.DataFrame({"entity_id": ["w1", "w2"], "meetings_scored": [2, 2], "skill": [0.1, -0.1]})
        members = pd.DataFrame({"wallet_address": ["w1", "w2", "w3"], "cluster_id": ["A", "A", "B"]})
        self.assertEqual(filter_by_skill(members, scores).wallet_address.tolist(), ["w1"])
        self.assertEqual(skill_weights(members, scores, floor=0.05).tolist(), [0.1, 0.0, 0.05])


if __name__ == "__main__":
    unittest.main()
