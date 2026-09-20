"""Tests sin red de la cola de confirmación: proponer, confirmar, cancelar, ambigüedad."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fantasy_agent import confirm
from fantasy_agent.config import Settings
from fantasy_agent.storage import Store


def make_settings() -> Settings:
    return Settings(
        data_dir=Path(tempfile.mkdtemp()), league_id=None, team_id=None,
        telegram_token="TESTTOKEN", telegram_chat_id="123",
        clause_window_hours=24, watch_interval_min=30, report_hour=9, request_delay_s=0,
    )


class FakeAPI:
    def __init__(self):
        self.calls = []

    def pay_buyout_clause(self, league_id, player_id, amount):
        self.calls.append(("clause", league_id, player_id, amount))

    def bid(self, league_id, market_id, money):
        self.calls.append(("bid", league_id, market_id, money))


def telegram_message(text, update_id=1):
    return {"update_id": update_id, "message": {"text": text}}


class Tests(unittest.TestCase):
    def setUp(self):
        self.s = make_settings()
        self.store = Store(self.s.db_file)
        self.api = FakeAPI()
        self.sent = []
        patcher = patch("fantasy_agent.notify.send_telegram", side_effect=lambda s, t: self.sent.append(t))
        self.mock_send = patcher.start()
        self.addCleanup(patcher.stop)

    def _updates(self, texts):
        return [telegram_message(t, update_id=i) for i, t in enumerate(texts, start=1)]

    def test_confirm_single_pending_executes(self):
        confirm.propose(self.s, self.store, "clause",
                         {"league_id": "L1", "player_id": "P1", "amount": 8_800_000, "player_name": "J3"},
                         "Clausulazo de prueba")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates(["Confirmado"])):
            results = confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [("clause", "L1", "P1", 8_800_000)])
        self.assertEqual(len(results), 1)
        self.assertFalse(self.store.get_pending())

    def test_cancel_removes_without_executing(self):
        confirm.propose(self.s, self.store, "clause",
                         {"league_id": "L1", "player_id": "P1", "amount": 1, "player_name": "J3"},
                         "Clausulazo de prueba")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates(["Cancelar"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [])
        self.assertFalse(self.store.get_pending())

    def test_ambiguous_multiple_pending_asks_for_code(self):
        id1 = confirm.propose(self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1}, "A")
        id2 = confirm.propose(self.s, self.store, "clause", {"league_id": "L1", "player_id": "P2", "amount": 1}, "B")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates(["Confirmar"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [])  # no ejecuta nada sin saber cuál
        pending_ids = {p["id"] for p in self.store.get_pending()}
        self.assertEqual(pending_ids, {id1, id2})

    def test_confirm_with_explicit_code_among_several(self):
        id1 = confirm.propose(self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1}, "A")
        confirm.propose(self.s, self.store, "clause", {"league_id": "L1", "player_id": "P2", "amount": 2}, "B")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {id1}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [("clause", "L1", "P1", 1)])
        remaining = {p["id"] for p in self.store.get_pending()}
        self.assertEqual(len(remaining), 1)

    def test_unrelated_message_is_ignored(self):
        confirm.propose(self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1}, "A")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates(["hola qué tal"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(len(self.store.get_pending()), 1)


if __name__ == "__main__":
    unittest.main()
