"""Tests sin red del autoajuste: cada ajuste necesita muestra mínima, se mueve despacio y respeta límites."""
import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fantasy_agent import autopilot as ap
from fantasy_agent import learn
from fantasy_agent.storage import Store


class ParamsTests(unittest.TestCase):
    def tearDown(self):
        ap.reset_params()

    def test_values_are_clamped_to_the_safety_bounds(self):
        ap.apply_params({"league_offer_min": 5.0, "bid_base_premium": -1, "invest_mult": 9})
        self.assertEqual(ap.PARAMS["league_offer_min"], ap.BOUNDS["league_offer_min"][1])
        self.assertEqual(ap.PARAMS["bid_base_premium"], ap.BOUNDS["bid_base_premium"][0])
        self.assertEqual(ap.PARAMS["invest_mult"], ap.BOUNDS["invest_mult"][1])

    def test_unknown_keys_are_ignored_and_reset_restores_the_factory_values(self):
        ap.apply_params({"hacker": 1, "league_offer_min": 1.08})
        self.assertNotIn("hacker", ap.PARAMS)
        ap.reset_params()
        self.assertEqual(ap.PARAMS, ap.DEFAULTS)

    def test_params_are_actually_used(self):
        from fantasy_agent.models import Offer, Player
        p = Player(id="x", name="x", position_id=3, team="T", team_id="t", market_value=10_000_000, points=5, avg_points=4.0, status="ok")
        offer = Offer(id="o", money=10_600_000, from_manager="LaLiga", is_system=True)
        self.assertEqual(ap.offer_decision(offer, p, loss=1.0)[0], "accept")
        ap.apply_params({"league_offer_min": 1.08})
        self.assertEqual(ap.offer_decision(offer, p, loss=1.0)[0], "hold")

    def test_every_default_is_inside_its_bounds(self):
        for k, v in ap.DEFAULTS.items():
            self.assertTrue(ap.BOUNDS[k][0] <= v <= ap.BOUNDS[k][1], k)


class OfferThresholdTests(unittest.TestCase):
    def test_needs_a_minimum_sample(self):
        self.assertIsNone(learn.optimal_offer_threshold([1.0] * 10))

    def test_uniform_offers_give_a_threshold_between_median_and_max(self):
        rnd = random.Random(1)
        ratios = [rnd.uniform(0.90, 1.12) for _ in range(500)]
        v, _ = learn.optimal_offer_threshold(ratios)
        self.assertTrue(1.04 < v < 1.10, v)

    def test_patience_pays_more_when_waiting_is_cheaper(self):
        rnd = random.Random(2)
        ratios = [rnd.uniform(0.90, 1.12) for _ in range(500)]
        cheap, _ = learn.optimal_offer_threshold(ratios, daily_discount=0.002)
        costly, _ = learn.optimal_offer_threshold(ratios, daily_discount=0.03)
        self.assertGreater(cheap, costly)


class BidPremiumTests(unittest.TestCase):
    def test_not_enough_data(self):
        self.assertIsNone(learn.adjust_bid_premium(0.03, [True] * 4))
        self.assertIsNone(learn.adjust_bid_premium(0.03, [False] * 8))  # aún <12 pujas resueltas

    def test_losing_too_many_raises_the_premium(self):
        new, _ = learn.adjust_bid_premium(0.03, [False] * 8 + [True] * 4)
        self.assertAlmostEqual(new, 0.04)

    def test_winning_everything_lowers_it(self):
        new, _ = learn.adjust_bid_premium(0.03, [True] * 14)
        self.assertAlmostEqual(new, 0.02)

    def test_a_healthy_rate_changes_nothing(self):
        self.assertIsNone(learn.adjust_bid_premium(0.03, [True] * 10 + [False] * 4))


class InvestMultiplierTests(unittest.TestCase):
    def test_bad_results_cut_the_allocation_gradually(self):
        new, _ = learn.invest_multiplier(1.0, [-0.08, -0.12, -0.05, -0.1, -0.09, -0.07] * 2)
        self.assertTrue(0.3 <= new < 1.0)
        self.assertGreater(new, 0.5)  # solo recorta a la mitad del camino

    def test_good_results_raise_it_up_to_the_cap(self):
        new, _ = learn.invest_multiplier(1.0, [0.3] * 14)
        self.assertGreater(new, 1.0)
        self.assertLessEqual(new, 1.5)
        self.assertIsNone(learn.invest_multiplier(1.5, [0.3] * 60))  # ya en el tope: nada que mover

    def test_few_investments_change_nothing(self):
        self.assertIsNone(learn.invest_multiplier(1.0, [0.5] * 8))   # <12 operaciones: no se fía


class DriftCalibrationTests(unittest.TestCase):
    def history(self, start, daily_growth, n=40):
        t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
        return [(t0 + timedelta(days=i), int(start * (1 + daily_growth) ** i)) for i in range(n)]

    def test_tier_matches_expected_drift(self):
        self.assertEqual(ap.drift_tier(5, 8, 8.0), "strong_good")
        self.assertEqual(ap.drift_tier(5, 8, 0.5), "strong_bad")
        self.assertEqual(ap.drift_tier(2.5, 3, 7.0), "early")
        self.assertIsNone(ap.drift_tier(0, 1, 9.0))

    def test_samples_are_grouped_by_tier(self):
        hist = {"p": self.history(10_000_000, 0.03)}                  # sube un 3% diario: nivel fuerte
        ends = {1: datetime(2026, 9, 5, tzinfo=timezone.utc), 2: datetime(2026, 9, 12, tzinfo=timezone.utc)}
        samples = learn.sample_drift(hist, {"p": [(1, 9), (2, 9)]}, ends)
        self.assertIn("strong_good", samples)
        self.assertGreater(sum(samples["strong_good"]) / len(samples["strong_good"]), 0.15)

    def test_calibration_needs_a_sample_and_blends_with_the_prior(self):
        self.assertEqual(learn.calibrate_drift({"strong_good": [0.5] * 10}), {})
        self.assertEqual(learn.calibrate_drift({"strong_good": [0.5] * 200}), {})   # 200 filas solapadas ≈ 29 independientes
        out = learn.calibrate_drift({"strong_good": [0.05] * 300})
        new, _ = out["drift_strong_good"]
        self.assertLess(new, ap.DEFAULTS["drift_strong_good"])        # los datos dicen menos que el valor de fábrica
        self.assertGreater(new, 0.0)

    def test_repeated_calibration_does_not_compound_the_haircut(self):
        samples = {"strong_good": [0.25] * 300}
        a = learn.calibrate_drift(samples)["drift_strong_good"][0]
        b = learn.calibrate_drift(samples)["drift_strong_good"][0]
        self.assertEqual(a, b)


class StoreParamsTests(unittest.TestCase):
    def test_roundtrip_and_history(self):
        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        store.set_params({"league_offer_min": 1.07})
        store.log_param_change("league_offer_min", 1.05, 1.07, "prueba")
        self.assertEqual(store.get_params()["league_offer_min"], 1.07)
        self.assertEqual(store.param_history()[0]["why"], "prueba")

    def test_bid_results_only_count_resolved_bids_with_a_known_ask(self):
        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        store.add_market_bid("a", "A", 1_030_000, None, ask=1_000_000)
        store.add_market_bid("b", "B", 1_030_000, None, ask=1_000_000)
        store.add_market_bid("c", "C", 1_030_000, None)                      # sin ask: no cuenta
        store.add_market_bid("d", "D", 1_030_000, None, ask=1_000_000)       # sin resolver
        ids = {b["player_id"]: b["id"] for b in store.unresolved_market_bids("buy")}
        store.resolve_market_bid(ids["a"], "won")
        store.resolve_market_bid(ids["b"], "lost")
        store.resolve_market_bid(ids["c"], "won")
        self.assertEqual(store.bid_results(), [True, False])


if __name__ == "__main__":
    unittest.main()
