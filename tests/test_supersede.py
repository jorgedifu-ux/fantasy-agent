"""Tests sin red: no se acumulan dos propuestas vivas para el mismo jugador."""
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
        briefing_interval_min=90, budget_reserve_pct=0.05, lineup_lock_hours=24,
        debt_ceiling_pct=0.20, debt_min_hours_lead=36,
    )


class SupersedeTests(unittest.TestCase):
    def setUp(self):
        self.s = make_settings()
        self.store = Store(self.s.db_file)
        patcher = patch("fantasy_agent.notify.send_telegram", side_effect=lambda *a, **k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_new_proposal_for_same_player_supersedes_old_one(self):
        id1 = confirm.propose(
            self.s, self.store, "clause", {"player_id": "P1", "amount": 100}, "cláusula a 100",
        )
        id2 = confirm.propose(
            self.s, self.store, "clause", {"player_id": "P1", "amount": 110}, "cláusula a 110 (subió)",
        )
        pending_ids = {p["id"] for p in self.store.get_pending()}
        self.assertEqual(pending_ids, {id2})  # solo queda la nueva
        self.assertNotIn(id1, pending_ids)

    def test_different_players_do_not_supersede_each_other(self):
        id1 = confirm.propose(self.s, self.store, "clause", {"player_id": "P1", "amount": 1}, "A")
        id2 = confirm.propose(self.s, self.store, "clause", {"player_id": "P2", "amount": 1}, "B")
        pending_ids = {p["id"] for p in self.store.get_pending()}
        self.assertEqual(pending_ids, {id1, id2})

    def test_different_kind_same_player_does_not_supersede(self):
        id1 = confirm.propose(self.s, self.store, "clause", {"player_id": "P1", "amount": 1}, "clausulazo")
        id2 = confirm.propose(self.s, self.store, "bid", {"player_id": "P1", "amount": 1}, "puja")
        pending_ids = {p["id"] for p in self.store.get_pending()}
        self.assertEqual(pending_ids, {id1, id2})


if __name__ == "__main__":
    unittest.main()
