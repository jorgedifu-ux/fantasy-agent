"""Puja del último minuto: el job espera hasta poco antes del cierre, relee el anuncio y puja."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fantasy_agent import autopilot as ap
from fantasy_agent import cli
from fantasy_agent.models import MarketItem, Player
from fantasy_agent.storage import Store

NOW = datetime.now(timezone.utc)


def item(my_bid=0, minutes=10):
    p = Player(id="p1", name="Pepe", position_id=3, team="T", team_id="t", market_value=5_000_000, points=20, avg_points=5.0, status="ok")
    return MarketItem(player=p, price=5_000_000, expires=NOW + timedelta(minutes=minutes), seller="LaLiga", bids=0,
                      market_id="m1", my_bid=my_bid)


class FakeAPI:
    def __init__(self, listed):
        self.listed, self.bids = listed, []

    def clear_cache(self): pass
    def market(self, league): return "RAW"
    def bid(self, league, market_id, money): self.bids.append((market_id, money))


class LateBidTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")
        self.world = SimpleNamespace(league_id="L", my_slots=[], recent_form={}, clause_freeze=None, trends={})
        p = patch("fantasy_agent.cli.time.sleep")
        self.sleep = p.start()
        self.addCleanup(p.stop)

    def run_with(self, listed):
        api = FakeAPI(listed)
        mv = ap.Move("bid", item().player, 5_200_000, item=item(), gain=2.0)
        with patch("fantasy_agent.cli.models.parse_market", return_value=listed):
            events = cli._timed_actions(self.store, api, self.world, [mv])
        return api, events

    def test_waits_and_bids(self):
        api, events = self.run_with([item()])
        self.assertEqual(api.bids, [("m1", 5_200_000)])
        self.assertTrue(any("último minuto" in e for e in events))
        waited = self.sleep.call_args[0][0]
        self.assertAlmostEqual(waited, 10 * 60 - ap.LATE_BID_LEAD_S, delta=5)

    def test_no_bid_if_already_bid_or_gone(self):
        self.assertEqual(self.run_with([item(my_bid=5_000_000)])[0].bids, [])
        self.assertEqual(self.run_with([])[0].bids, [])


if __name__ == "__main__":
    unittest.main()


class FinalLineupWait(unittest.TestCase):
    def test_waits_until_two_minutes_before_kickoff(self):
        self.assertEqual(ap.final_lineup_wait(14 * 60), 12 * 60)

    def test_acts_now_when_less_than_two_minutes_are_left(self):
        self.assertEqual(ap.final_lineup_wait(90), 0.0)

    def test_nothing_when_far_away_or_already_started(self):
        self.assertIsNone(ap.final_lineup_wait(40 * 60))
        self.assertIsNone(ap.final_lineup_wait(0))
        self.assertIsNone(ap.final_lineup_wait(-30))
        self.assertIsNone(ap.final_lineup_wait(None))


class InvestMode(unittest.TestCase):
    def world(self, hours, in_break=False):
        from fantasy_agent.service import Outlook
        o = Outlook(next_first=None, prev_last=None, in_break=in_break)
        o.__class__ = type("O", (Outlook,), {"hours_to_next": property(lambda self: hours)})
        return SimpleNamespace(outlook=o)

    def test_on_in_a_break_or_when_the_next_matchday_is_a_week_away(self):
        self.assertTrue(cli._invest_mode(self.world(100, in_break=True)))
        self.assertTrue(cli._invest_mode(self.world(309)))

    def test_off_close_to_a_matchday(self):
        self.assertFalse(cli._invest_mode(self.world(100)))
        self.assertFalse(cli._invest_mode(SimpleNamespace(outlook=None)))


class DailyOffers(unittest.TestCase):
    def test_seconds_until_2053_madrid(self):
        from datetime import datetime, timezone
        # 8/11/2026 es CET (UTC+1): las 20:46 de Madrid son las 19:46 UTC
        self.assertEqual(ap.seconds_to_daily_offers(datetime(2026, 11, 8, 19, 46, tzinfo=timezone.utc)), 7 * 60)

    def test_none_once_the_offers_have_arrived(self):
        from datetime import datetime, timezone
        self.assertIsNone(ap.seconds_to_daily_offers(datetime(2026, 11, 8, 20, 1, tzinfo=timezone.utc)))
