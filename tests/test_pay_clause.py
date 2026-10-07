"""Pago de cláusula: se relee justo antes y se paga lo que vale en ese instante, nunca más de lo planeado."""
import unittest
from datetime import datetime, timedelta, timezone

from fantasy_agent import cli
from fantasy_agent.http import HttpError
from fantasy_agent.models import Player, SquadSlot

NOW = datetime.now(timezone.utc)


def slot(clause=4_000_000):
    p = Player(id="p1", name="Pepe", position_id=3, team="T", team_id="t", market_value=4_000_000, points=10,
               avg_points=5.0, status="ok")
    return SquadSlot(player=p, owner_team_id="t9", owner_name="Rival", clause=clause, clause_locked_until=None,
                     player_team_id="pt1")


class FakeAPI:
    def __init__(self, clause=4_000_000, lock=None, shield=None, present=True):
        self.item = {"playerMaster": {"id": "p1", "nickname": "Pepe", "positionId": 3, "marketValue": 4_000_000},
                     "playerTeamId": "pt1", "buyoutClause": clause, "buyoutClauseLockedEndTime": lock}
        if shield:
            self.item.update(isShielded=True, shieldedEndDate=shield)
        self.present = present
        self.paid = []

    def team_fresh(self, league, team_id):
        return {"players": [self.item] if self.present else []}

    def pay_buyout_clause(self, league, ptid, amount):
        self.paid.append((ptid, amount))


class PayClauseTests(unittest.TestCase):
    def test_pays_the_current_amount_not_more(self):
        api = FakeAPI(clause=3_900_000)  # bajó: se paga lo de ahora, no lo planeado
        self.assertEqual(cli._pay_clause(api, "L", slot(), 4_000_000), 3_900_000)
        self.assertEqual(api.paid, [("pt1", 3_900_000)])

    def test_refuses_if_it_rose(self):
        api = FakeAPI(clause=4_500_000)
        with self.assertRaisesRegex(RuntimeError, "ha subido"):
            cli._pay_clause(api, "L", slot(), 4_000_000)
        self.assertEqual(api.paid, [])

    def test_refuses_if_locked_or_shielded(self):
        for api in (FakeAPI(lock=(NOW + timedelta(hours=3)).isoformat()),
                    FakeAPI(shield=(NOW + timedelta(days=2)).isoformat())):
            with self.assertRaises(RuntimeError):
                cli._pay_clause(api, "L", slot(), 4_000_000)
            self.assertEqual(api.paid, [])

    def test_refuses_if_already_gone(self):
        api = FakeAPI(present=False)
        with self.assertRaisesRegex(RuntimeError, "ya no está"):
            cli._pay_clause(api, "L", slot(), 4_000_000)


class TransientTests(unittest.TestCase):
    def test_classification(self):
        self.assertTrue(cli._is_transient(HttpError(503, "u", "x")))
        self.assertTrue(cli._is_transient(HttpError(429, "u", "x")))
        self.assertFalse(cli._is_transient(HttpError(400, "u", "x")))
        self.assertTrue(cli._is_transient(TimeoutError()))
        self.assertTrue(cli._is_transient(RuntimeError("Fallo tras reintentos: ...")))
        self.assertFalse(cli._is_transient(KeyError("x")))


class RedactTests(unittest.TestCase):
    def test_no_secrets_in_published_errors(self):
        from fantasy_agent.storage import redact
        s = redact('HTTP 400 en https://api.telegram.org/bot123456:AAH-x_y/sendMessage: {"refresh_token": "abc.def", '
                   '"x": 1} Authorization: Bearer eyJ.hh.zz code=XYZ&state=1')
        for secret in ("123456:AAH", "abc.def", "eyJ.hh.zz", "XYZ"):
            self.assertNotIn(secret, s)
        self.assertIn("sendMessage", s)


if __name__ == "__main__":
    unittest.main()
