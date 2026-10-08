"""Crédito solo en parones largos y devolución antes de la jornada (con saldo negativo al empezar, 0 puntos)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fantasy_agent import autopilot as ap
from fantasy_agent import cli
from fantasy_agent.models import MarketItem, Offer, Player, SquadSlot
from fantasy_agent.storage import Store


class CreditRules(unittest.TestCase):
    def test_credit_only_in_long_breaks(self):
        self.assertEqual(ap.credit_room(260_000_000, 1_000_000, 100, 0.10), 0)          # semana normal
        self.assertEqual(ap.credit_room(260_000_000, 1_000_000, 200, 0.10), 26_000_000)  # parón
        self.assertEqual(ap.credit_room(260_000_000, -20_000_000, 200, 0.10), 6_000_000)  # ya se debe parte
        self.assertEqual(ap.credit_room(260_000_000, 1_000_000, 200, 0.0), 0)           # apagado

    def test_repayment_gets_less_picky_near_the_jornada(self):
        self.assertIsNone(ap.delever_min(100))
        self.assertGreater(ap.delever_min(60), ap.delever_min(30))
        self.assertGreater(ap.delever_min(30), ap.delever_min(10))


NOW = datetime.now(timezone.utc)


def pl(pid, pos, avg, value):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=10, avg_points=avg, status="ok")


class Delever(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")

    def world(self, cash, hours):
        squad = [pl("gk", 1, 5, 5_000_000)] + [pl(f"d{i}", 2, 5, 5_000_000) for i in range(3)] + \
            [pl(f"m{i}", 3, 5, 5_000_000) for i in range(4)] + [pl(f"f{i}", 4, 5, 5_000_000) for i in range(3)] + \
            [pl("bench", 3, 1, 10_000_000), pl("bench2", 3, 0.5, 8_000_000)]
        slots = [SquadSlot(player=p, owner_team_id="me", owner_name="yo", clause=p.market_value, clause_locked_until=None,
                           player_team_id="pt" + p.id) for p in squad]
        market = [MarketItem(player=p, price=p.market_value, expires=None, seller="yo", bids=0, market_id="mk" + p.id,
                             offers_count=1, seller_team_id="me") for p in squad]
        return SimpleNamespace(my_cash=cash, my_slots=slots, market=market, my_team_id="me", league_id="L", recent_form={},
                               clause_freeze=(NOW + timedelta(hours=hours - 24), NOW + timedelta(hours=hours)))

    def run_(self, cash, hours, ratio=0.99):
        class API:
            def __init__(self):
                self.accepted = []
            def player_team_offers(self, league, ptid):
                return "x" + ptid
            def accept_offer(self, league, mid, oid, money):
                self.accepted.append(mid)
        api = API()
        world = self.world(cash, hours)
        values = {"pt" + sl.player.id: sl.player.market_value for sl in world.my_slots}
        with patch("fantasy_agent.cli.models.parse_player_offers",
                   side_effect=lambda raw: [Offer(id="o" + raw, money=int(values[raw[1:]] * ratio), from_manager="LaLiga", is_system=True)]), \
                patch("fantasy_agent.cli._committed_bids", return_value=(0, [])):
            events = cli._delever(self.store, None, api, world)
        return api.accepted, events

    def test_sells_bench_first_until_positive(self):
        accepted, events = self.run_(-9_000_000, 50)
        self.assertEqual(accepted, ["mkbench2", "mkbench"][:len(accepted)])
        self.assertIn("mkbench2", accepted)
        self.assertTrue(any("Devuelvo" in e for e in events))

    def test_nothing_when_far_or_positive(self):
        self.assertEqual(self.run_(-9_000_000, 120)[0], [])
        self.assertEqual(self.run_(3_000_000, 20)[0], [])

    def test_never_breaks_the_eleven(self):
        accepted, events = self.run_(-200_000_000, 10, ratio=0.9)
        self.assertEqual(sorted(accepted), ["mkbench", "mkbench2"])
        self.assertTrue(any("Sigo en negativo" in e for e in events))


if __name__ == "__main__":
    unittest.main()
