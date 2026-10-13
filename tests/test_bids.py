"""Puja mínima válida: nunca por debajo del valor actual (caso Gulácsi, 13/10/2026) y reintento si la API rechaza el importe."""
import unittest
from datetime import datetime, timedelta, timezone

from fantasy_agent import autopilot as ap
from fantasy_agent import cli
from fantasy_agent.http import HttpError
from fantasy_agent.models import MarketItem, Player

NOW = datetime(2026, 10, 13, 20, 45, tzinfo=timezone.utc)


def item(price, value, bids=0):
    p = Player(id="g", name="Gulácsi", position_id=1, team="T", team_id="t", market_value=value, points=24, avg_points=3.0, status="ok")
    return MarketItem(player=p, price=price, expires=NOW + timedelta(minutes=8), seller="LaLiga", bids=bids, market_id="m1")


class FloorTests(unittest.TestCase):
    def test_floor_is_the_current_value_when_the_listing_is_stale(self):
        it = item(8_599_235, 8_913_052)                          # el anuncio es de ayer; hoy ya vale +3,6%
        self.assertEqual(ap.bid_floor(it), 8_913_052)
        self.assertGreaterEqual(ap.bid_amount(it, gain=1.0), 8_913_052)    # antes: 8.857.212 → rechazada
        self.assertEqual(ap.bid_moves([it])[0].cost, 8_913_052)

    def test_floor_is_the_price_when_the_value_has_not_moved(self):
        self.assertEqual(ap.bid_floor(item(10_000_000, 9_900_000)), 10_000_000)

    def test_invest_bids_go_above_the_floor(self):
        it = item(8_599_235, 8_913_052)
        tr = {"g": __import__("fantasy_agent.analysis", fromlist=["Trend"]).Trend(3.5, 9.0, 17.0)}
        ap.set_match_context(None, {})
        mv = ap.invest_moves([it], tr, form={"g": 6.0})
        if mv:      # puede no pasar el filtro de prima/tendencia; si pasa, nunca por debajo del suelo
            self.assertGreater(mv[0].cost, 8_913_052)


class FakeAPI:
    def __init__(self, min_valid):
        self.min_valid, self.tried = min_valid, []

    def bid(self, league, market_id, amount):
        self.tried.append(amount)
        if amount < self.min_valid:
            raise HttpError(400, "https://x/bid", '{"code":400,"message":"\\"%d\\" is not a valid money quantity for this player"}' % amount)


class RobustBid(unittest.TestCase):
    def test_retries_upwards_until_accepted(self):
        it = item(8_599_235, 8_913_052)
        api = FakeAPI(min_valid=9_000_000)                       # alguien ya pujó por encima del valor
        paid = cli._bid_robust(api, "L", it, 8_913_052)
        self.assertGreaterEqual(paid, 9_000_000)
        self.assertLessEqual(paid, round(8_913_052 * 1.12))
        self.assertGreater(len(api.tried), 1)

    def test_gives_up_above_the_cap_and_other_errors_are_not_retried(self):
        it = item(8_599_235, 8_913_052)
        with self.assertRaises(HttpError):
            cli._bid_robust(FakeAPI(min_valid=20_000_000), "L", it, 8_913_052)

        class Boom:
            def bid(self, *a):
                raise HttpError(403, "u", "no autorizado")
        with self.assertRaises(HttpError):
            cli._bid_robust(Boom(), "L", it, 8_913_052)


if __name__ == "__main__":
    unittest.main()
