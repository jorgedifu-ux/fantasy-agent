"""Tests sin red: aviso de "ha llegado una oferta" sobre tus anuncios de venta pendientes.

La API no expone el importe exacto de una oferta "marketPlayerTeam" (solo `numberOfOffers`),
así que el aviso no puede decir "buena/mala" con una cifra real — lo que sí puede dar es el
umbral que deberías exigir (`analysis.min_acceptable_offer`) para que decidas tú comparando
con lo que veas en la app."""
import tempfile
import unittest
from pathlib import Path

from fantasy_agent.cli import _notify_new_offers
from fantasy_agent.models import MarketItem, Player
from fantasy_agent.storage import Store


def make_player(pid: str) -> Player:
    return Player(
        id=pid, name=f"Jugador {pid}", position_id=3, team="Equipo", team_id="t1",
        market_value=10_000_000, points=50, avg_points=5.0, status="ok",
    )


class FakeWorld:
    def __init__(self, market, my_team_id="me"):
        self.market = market
        self.my_team_id = my_team_id


class NotifyNewOffersTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "test.db")

    def test_no_offer_yet_is_silent(self):
        self.store.add_market_bid("P1", "Jugador P1", 10_000_000, None, direction="sell", sell_kind="profit_take")
        item = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="LaLiga",
                           bids=0, offers_count=0, seller_team_id="me")
        world = FakeWorld([item])
        self.assertEqual(_notify_new_offers(self.store, None, world), [])

    def test_new_offer_reports_threshold_and_reason(self):
        self.store.add_market_bid("P1", "Jugador P1", 10_000_000, None, direction="sell", sell_kind="profit_take")
        item = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="LaLiga",
                           bids=0, offers_count=1, seller_team_id="me")
        world = FakeWorld([item])
        [msg] = _notify_new_offers(self.store, None, world)
        self.assertIn("Jugador P1", msg)
        self.assertIn("1 oferta", msg)
        self.assertIn("10.00M", msg)  # umbral profit_take = 100% del precio puesto

    def test_same_offer_count_is_not_repeated(self):
        self.store.add_market_bid("P1", "Jugador P1", 10_000_000, None, direction="sell", sell_kind="profit_take")
        item = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="LaLiga",
                           bids=0, offers_count=1, seller_team_id="me")
        world = FakeWorld([item])
        self.assertEqual(len(_notify_new_offers(self.store, None, world)), 1)
        self.assertEqual(_notify_new_offers(self.store, None, world), [])  # ya avisado, mismo nº de ofertas

    def test_offer_count_going_up_notifies_again(self):
        self.store.add_market_bid("P1", "Jugador P1", 10_000_000, None, direction="sell", sell_kind="cut_loss")
        item1 = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="LaLiga",
                            bids=0, offers_count=1, seller_team_id="me")
        world1 = FakeWorld([item1])
        self.assertEqual(len(_notify_new_offers(self.store, None, world1)), 1)
        item2 = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="LaLiga",
                            bids=0, offers_count=2, seller_team_id="me")
        world2 = FakeWorld([item2])
        [msg] = _notify_new_offers(self.store, None, world2)
        self.assertIn("2 ofertas", msg)
        self.assertIn("9.00M", msg)  # umbral cut_loss = 90% del precio puesto

    def test_listing_not_owned_by_me_is_ignored(self):
        self.store.add_market_bid("P1", "Jugador P1", 10_000_000, None, direction="sell")
        item = MarketItem(player=make_player("P1"), price=10_000_000, expires=None, seller="Pepe",
                           bids=0, offers_count=1, seller_team_id="rival")
        world = FakeWorld([item])
        self.assertEqual(_notify_new_offers(self.store, None, world), [])


if __name__ == "__main__":
    unittest.main()
