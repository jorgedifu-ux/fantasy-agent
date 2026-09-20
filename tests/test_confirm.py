"""Tests sin red de la cola de confirmación: proponer, confirmar, cancelar, ambigüedad."""
import tempfile
import time
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
        briefing_interval_min=90, budget_reserve_pct=0.2, emergency_buy_cap_pct=0.15,
        emergency_buys_per_week=3, lineup_lock_hours=24,
    )


class FakeAPI:
    def __init__(self):
        self.calls = []

    def pay_buyout_clause(self, league_id, player_id, amount):
        self.calls.append(("clause", league_id, player_id, amount))

    def bid(self, league_id, market_id, money):
        self.calls.append(("bid", league_id, market_id, money))


BID_PAYLOAD = {
    "league_id": "L1", "market_id": "m1", "money": 5_000_000,
    "player_id": "P9", "player_name": "Fulanito", "expires_at": time.time() + 3600,
}


def telegram_message(text, update_id=1):
    return {"update_id": update_id, "message": {"text": text}}


class Tests(unittest.TestCase):
    def setUp(self):
        self.s = make_settings()
        self.store = Store(self.s.db_file)
        self.api = FakeAPI()
        self.sent = []
        patcher = patch(
            "fantasy_agent.notify.send_telegram",
            side_effect=lambda s, t, buttons=None, html=False: self.sent.append(t),
        )
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

    def test_confirm_far_future_schedules_instead_of_executing(self):
        op_id = confirm.propose(
            self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1},
            "Se libera en un rato", execute_at=time.time() + 3600,
        )
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {op_id}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [])  # no se ejecuta todavía
        self.assertFalse(self.store.get_pending())
        scheduled = self.store.get_scheduled()
        self.assertEqual([s["id"] for s in scheduled], [op_id])

    def test_confirm_near_future_executes_immediately(self):
        op_id = confirm.propose(
            self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1},
            "Ya casi", execute_at=time.time() + 5,
        )
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {op_id}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [("clause", "L1", "P1", 1)])
        self.assertFalse(self.store.get_scheduled())

    def test_run_scheduled_waits_and_executes_at_the_right_time(self):
        op_id = confirm.propose(
            self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 42},
            "Programado", execute_at=time.time() + 3600,
        )
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {op_id}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [])

        # Reprogramamos el mismo pendiente a "ya casi" para no dormir de verdad 1h en el test.
        self.store.db.execute("UPDATE pending_ops SET execute_at = ? WHERE id = ?", (time.time() + 0.05, op_id))
        self.store.db.commit()

        before = time.time()
        results = confirm.run_scheduled(self.s, self.store, self.api, max_wait_s=10)
        self.assertGreaterEqual(time.time() - before, 0.04)  # de verdad ha esperado, no lo ha saltado
        self.assertEqual(self.api.calls, [("clause", "L1", "P1", 42)])
        self.assertEqual(len(results), 1)
        self.assertFalse(self.store.get_scheduled())

    def test_run_scheduled_ignores_far_future_ops(self):
        confirm.propose(
            self.s, self.store, "clause", {"league_id": "L1", "player_id": "P1", "amount": 1},
            "Muy lejos", execute_at=time.time() + 7200,
        )
        op_id = self.store.get_pending()[0]["id"]
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {op_id}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)

        results = confirm.run_scheduled(self.s, self.store, self.api, max_wait_s=60)
        self.assertEqual(results, [])
        self.assertEqual(self.api.calls, [])
        self.assertEqual(len(self.store.get_scheduled()), 1)  # sigue programado, para más tarde


    def test_bid_execution_is_tracked_as_pending_not_done(self):
        op_id = confirm.propose(self.s, self.store, "bid", BID_PAYLOAD, "Fichaje de prueba")
        with patch("fantasy_agent.notify.get_telegram_updates", return_value=self._updates([f"Confirmar {op_id}"])):
            confirm.poll_and_execute(self.s, self.store, self.api)
        self.assertEqual(self.api.calls, [("bid", "L1", "m1", 5_000_000)])
        pending_bids = self.store.unresolved_market_bids()
        self.assertEqual(len(pending_bids), 1)
        self.assertEqual(pending_bids[0]["player_id"], "P9")
        # El mensaje debe dejar claro que está pendiente, no que ya se ha ganado el jugador.
        self.assertIn("pendiente", self.sent[-1].lower())


if __name__ == "__main__":
    unittest.main()
