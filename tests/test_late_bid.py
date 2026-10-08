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
        self.world = SimpleNamespace(league_id="L")
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
