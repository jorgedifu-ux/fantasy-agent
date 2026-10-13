"""Cohortes de valor tras un partido: datos sintéticos."""
import unittest
from datetime import date, timedelta

from fantasy_agent import cohorts


def player(points_wk8, start, daily):
    d = date(2026, 10, 10)
    v = {(d + timedelta(days=k)).isoformat(): int(start * (1 + daily) ** (k + 4)) for k in range(-4, 9)}
    return {"w": {1: 5, 2: 5, 3: 5, 4: 5, 8: points_wk8}, "team": "9", "v": v, "name": "x", "pos": "3"}


class CohortTests(unittest.TestCase):
    def setUp(self):
        cal = {"8:9": "2026-10-10"}
        self.obs = cohorts.observations({f"u{i}": player(0, 10_000_000, -0.012) for i in range(10)}
                                        | {f"r{i}": player(12, 10_000_000, 0.03) for i in range(10)}, cal)

    def test_buckets_and_rising_flag(self):
        zero = [o for o in self.obs if o["zb"] == "0"]
        good = [o for o in self.obs if o["zb"] == ">=1.8"]
        self.assertEqual((len(zero), len(good)), (10, 10))
        self.assertTrue(all(o["pre"] < 0 for o in zero) and all(o["pre"] > .05 for o in good))

    def test_cohort_expectation(self):
        falling = cohorts.cohort(self.obs, "0", rising=False, k=2)
        rising = cohorts.cohort(self.obs, ">=1.8", rising=True, k=2)
        self.assertLess(falling["mean"], 0)
        self.assertGreater(rising["mean"], 0.1)
        self.assertEqual(falling["down"], 1.0)
        self.assertIsNone(cohorts.cohort(self.obs, "0", rising=True, k=2))      # sin datos suficientes

    def test_report_renders(self):
        text = cohorts.report(self.obs)
        self.assertIn("Subían antes", text)
        self.assertIn("0 puntos (sin jugar)", text)


if __name__ == "__main__":
    unittest.main()
