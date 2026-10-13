"""Subida esperada según el último partido (tabla viva) y salida de 3 días para los que no subían y jugaron mal."""
import unittest
from datetime import date, timedelta

from fantasy_agent import autopilot as ap
from fantasy_agent import cohorts
from fantasy_agent.models import Offer, Player


def pl(pid="p", value=10_000_000, pos=3):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=30, avg_points=5.0, status="ok")


def offer(ratio, value=10_000_000):
    return Offer(id="o", money=int(value * ratio), from_manager="LaLiga", is_system=True)


class SignalTests(unittest.TestCase):
    D = date(2026, 10, 10)

    def raw(self, pts8):
        return {"teamId": "9", "weekPoints": [{"weekNumber": w, "points": v} for w, v in ((3, 5), (4, 6), (5, 4), (6, 5), (8, pts8))]}

    def values(self, daily):
        return {self.D + timedelta(days=k): int(10_000_000 * (1 + daily) ** (k + 4)) for k in range(-6, 6)}

    def test_zero_points_in_a_player_that_was_not_rising(self):
        sig = cohorts.signal(self.raw(0), {(8, "9"): self.D}, self.values(-0.01), self.D + timedelta(days=3))
        self.assertEqual(sig, ("0", False, 3))

    def test_good_game_of_a_riser(self):
        sig = cohorts.signal(self.raw(12), {(8, "9"): self.D}, self.values(0.03), self.D + timedelta(days=2))
        self.assertEqual(sig, (">=1.8", True, 2))

    def test_no_signal_when_the_match_is_old_or_history_is_short(self):
        self.assertIsNone(cohorts.signal(self.raw(0), {(8, "9"): self.D}, self.values(0.0), self.D + timedelta(days=9)))
        short = {"teamId": "9", "weekPoints": [{"weekNumber": 3, "points": 5}, {"weekNumber": 8, "points": 0}]}
        self.assertIsNone(cohorts.signal(short, {(8, "9"): self.D}, self.values(0.0), self.D + timedelta(days=2)))


class TableTests(unittest.TestCase):
    def test_new_cells_with_many_cases_replace_the_prior_and_small_ones_are_blended(self):
        prior = {"0|0|2": [-0.08, 250], "1-1.8|1|2": [0.20, 100]}
        merged = cohorts.merge_tables({"0|0|2": [-0.03, 300], "1-1.8|1|2": [0.40, 10]}, prior)
        self.assertEqual(merged["0|0|2"], [-0.03, 300])
        self.assertAlmostEqual(merged["1-1.8|1|2"][0], 0.25 * 0.40 + 0.75 * 0.20, places=3)    # 10 casos pesan 10/40

    def test_lookup_needs_enough_cases_and_a_valid_day(self):
        table = {"0|0|2": [-0.08, 250], "0|0|3": [-0.05, 5]}
        self.assertEqual(cohorts.lookup(table, "0", False, 2), (-0.08, 250))
        self.assertIsNone(cohorts.lookup(table, "0", False, 3))      # pocos casos
        self.assertIsNone(cohorts.lookup(table, "0", False, 5))      # demasiados días tras el partido


class DriftOverride(unittest.TestCase):
    def tearDown(self):
        ap.set_match_context(None, {})

    def test_uses_the_match_table_when_there_is_a_signal_and_the_trend_otherwise(self):
        table = {"0|0|2": [-0.082, 250]}
        ap.set_match_context(lambda pid: ("0", False, 2) if pid == "a" else None, table)
        self.assertAlmostEqual(ap.expected_drift(5.0, 8.0, 7.0, "a"), -0.082)       # tendencia fuerte pero 0 puntos y no subía: baja
        self.assertEqual(ap.expected_drift(5.0, 8.0, 7.0, "b"), ap.PARAMS["drift_strong_good"])   # sin señal: la de siempre

    def test_clamped(self):
        ap.set_match_context(lambda pid: (">=1.8", True, 2), {">=1.8|1|2": [0.9, 100]})
        self.assertEqual(ap.expected_drift(0, 0, None, "x"), ap.MATCH_DRIFT_CAP)


class ExitMode(unittest.TestCase):
    def test_who_is_a_candidate(self):
        self.assertTrue(ap.exit_candidate(("0.4-1", False, 3), 1.0))
        self.assertTrue(ap.exit_candidate(("0", False, 6), -2.0))
        self.assertFalse(ap.exit_candidate(("0", True, 3), 1.0))                 # subía antes: se aguanta
        self.assertFalse(ap.exit_candidate(("1-1.8", False, 3), 1.0))            # jugó bien
        self.assertFalse(ap.exit_candidate(("0", False, 3), 12.0))               # sube ahora con fuerza
        self.assertFalse(ap.exit_candidate(None, 0.0))

    def test_sells_at_value_inside_the_window_and_a_bit_below_after_it(self):
        p = pl()
        kw = dict(loss=0.2, trend_d7=0.0, trend_d3=-1.0, cost_basis=11_000_000, hours_to_deadline=100, exit_mode=True)
        self.assertEqual(ap.offer_decision(offer(1.00), p, **kw)[0], "accept")                  # a su valor, aunque se pagó más
        self.assertEqual(ap.offer_decision(offer(0.98), p, **kw)[0], "hold")                    # dentro del plazo se espera algo mejor
        self.assertEqual(ap.offer_decision(offer(0.98), p, exit_late=True, **kw)[0], "accept")  # pasados 3 días, ≥0,97×
        self.assertEqual(ap.offer_decision(offer(0.95), p, exit_late=True, **kw)[0], "hold")

    def test_key_players_and_the_xi_before_the_jornada_are_not_sold_this_way(self):
        p = pl()
        kw = dict(trend_d7=0.0, trend_d3=-1.0, hours_to_deadline=100, exit_mode=True)
        self.assertEqual(ap.offer_decision(offer(1.00), p, loss=5.0, **kw)[0], "hold")          # Hancko: titular clave
        self.assertEqual(ap.offer_decision(offer(1.10), p, loss=1.5, breaks_xi=True, **{**kw, "hours_to_deadline": 20})[0], "hold")

    def test_without_the_flag_nothing_changes(self):
        p = pl()
        self.assertEqual(ap.offer_decision(offer(1.00), p, loss=0.2, trend_d7=0.0, trend_d3=-1.0, hours_to_deadline=100)[0], "hold")   # 1,05 normal


if __name__ == "__main__":
    unittest.main()
