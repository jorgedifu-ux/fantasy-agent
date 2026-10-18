"""Alineación probable de futbolfantasy en las decisiones (18/10/2026)."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fantasy_agent import autopilot as ap
from fantasy_agent import cli
from fantasy_agent.models import Player
from fantasy_agent.storage import Store


def player(pid="p", avg=6.0, status="ok"):
    return Player(id=pid, name=pid, position_id=3, team="T", team_id="t", market_value=10_000_000, points=30, avg_points=avg, status=status)


class StartFactor(unittest.TestCase):
    def tearDown(self):
        ap.set_start_probs(None)

    def test_factor_is_one_at_the_normal_starter_probability(self):
        self.assertEqual(ap.start_factor(80), 1.0)

    def test_a_probable_starter_counts_a_bit_more_and_a_fringe_player_much_less(self):
        self.assertAlmostEqual(ap.start_factor(90), 1.125)
        self.assertAlmostEqual(ap.start_factor(60), 0.75)
        self.assertAlmostEqual(ap.start_factor(30), 0.375)
        self.assertEqual(ap.start_factor(100), ap.START_FACTOR_MAX)
        self.assertEqual(ap.start_factor(5), ap.START_FACTOR_MIN)

    def test_xpts_uses_the_probability_only_when_it_is_known(self):
        base = ap.xpts(player())
        ap.set_start_probs(lambda pid: 60 if pid == "p" else None)
        self.assertAlmostEqual(ap.xpts(player()), base * 0.75, places=1)
        self.assertEqual(ap.xpts(player("otro")), base)

    def test_the_lineup_can_skip_it_to_avoid_counting_it_twice(self):
        ap.set_start_probs(lambda pid: 30)
        self.assertEqual(ap.xpts(player(), start=False), 6.0)

    def test_an_injured_player_stays_at_zero(self):
        ap.set_start_probs(lambda pid: 100)
        self.assertEqual(ap.xpts(player(status="injured")), 0.0)


class FFCache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")
        p = player()
        self.world = SimpleNamespace(my_slots=[SimpleNamespace(player=p)], rival_slots=[], market=[], clause_freeze=None, outlook=None)

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def fetch(self, side_effect):
        return mock.patch.object(cli.futbolfantasy, "fetch_probable_lineups", side_effect=side_effect)

    def test_it_is_fetched_once_and_then_served_from_the_cache(self):
        with mock.patch.object(cli, "_hours_to_deadline", return_value=100), \
                self.fetch(lambda players: {"p": {"start_probability": 90, "status": "ok", "note": "futbolfantasy"}}) as m:
            a = cli._ff_probs(self.store, None, self.world)
            b = cli._ff_probs(self.store, None, self.world)
        self.assertEqual(a, b)
        self.assertEqual(m.call_count, 1)

    def test_it_refreshes_sooner_near_the_deadline(self):
        self.store.set("ff_probs", json.dumps({"at": time.time() - 3600, "p": {"p": {"start_probability": 50}}}))
        with mock.patch.object(cli, "_hours_to_deadline", return_value=20), \
                self.fetch(lambda players: {"p": {"start_probability": 90}}) as m:
            self.assertEqual(cli._ff_probs(self.store, None, self.world)["p"]["start_probability"], 90)
        self.assertEqual(m.call_count, 1)
        with mock.patch.object(cli, "_hours_to_deadline", return_value=100), self.fetch(lambda players: {"p": {}}) as m:
            self.store.set("ff_probs", json.dumps({"at": time.time() - 3600, "p": {"p": {"start_probability": 50}}}))
            self.assertEqual(cli._ff_probs(self.store, None, self.world)["p"]["start_probability"], 50)   # a 100 h aún vale (ttl 3 h)
        self.assertEqual(m.call_count, 0)

    def test_if_the_website_fails_the_old_data_is_kept_and_retried_in_ten_minutes(self):
        self.store.set("ff_probs", json.dumps({"at": time.time() - 4 * 3600, "p": {"p": {"start_probability": 70}}}))

        def boom(players):
            raise RuntimeError("web caída")
        with mock.patch.object(cli, "_hours_to_deadline", return_value=100), self.fetch(boom):
            got = cli._ff_probs(self.store, None, self.world)
        self.assertEqual(got["p"]["start_probability"], 70)
        retry_in = 3 * 3600 - (time.time() - json.loads(self.store.get("ff_probs"))["at"])
        self.assertLess(retry_in, 11 * 60)


if __name__ == "__main__":
    unittest.main()


class NextMatchPage(unittest.TestCase):
    INDEX = (
        '<a href="https://www.futbolfantasy.com/partidos/1-barcelona-real-madrid" class="partido" data-tooltip="Barcelona - Real Madrid">'
        '<div class="fecha"> Dom 25/10 <br>21:00h </div></a>'
        '<a href="https://www.futbolfantasy.com/partidos/2-real-madrid-sevilla" class="partido" data-tooltip="Real Madrid - Sevilla">'
        '<div class="fecha"> Dom 18/10 <br>21:00h </div></a>'
        '<a href="https://www.futbolfantasy.com/partidos/3-getafe-madrid-ya-jugado" class="partido" data-tooltip="Deportivo - Real Madrid">'
        '<div class="fecha"> Sab 17/10 <br>14:00h </div></a>'
    )

    def test_the_next_unplayed_match_wins_not_the_first_one_in_the_page(self):
        from datetime import datetime, timezone, timedelta
        from fantasy_agent import futbolfantasy as ff
        now = datetime(2026, 10, 18, 3, 0, tzinfo=timezone(timedelta(hours=2)))
        urls = ff._find_match_urls(self.INDEX, {"madrid", "sevilla", "barcelona", "deportivo"}, now=now)
        self.assertTrue(urls["madrid"].endswith("2-real-madrid-sevilla"))
        self.assertTrue(urls["barcelona"].endswith("1-barcelona-real-madrid"))
        self.assertNotIn("deportivo", urls)          # su partido ya se jugó
