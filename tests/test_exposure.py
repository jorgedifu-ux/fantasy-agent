"""Registro diario de exposición de cláusulas."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fantasy_agent import exposure
from fantasy_agent.models import Player, SquadSlot
from fantasy_agent.storage import Store

NOW = datetime(2026, 11, 8, 20, 30, tzinfo=timezone.utc)


def slot(pid, locked=None, shielded=None, clause_mult=1.0):
    p = Player(id=pid, name=pid, position_id=3, team="T", team_id="t", market_value=10_000_000, points=40, avg_points=4.0, status="ok")
    return SquadSlot(player=p, owner_team_id="me", owner_name="me", clause=int(10_000_000 * clause_mult), clause_locked_until=locked,
                     shielded_until=shielded, player_team_id="pt" + pid)


class Exposure(unittest.TestCase):
    def test_logs_open_and_shielded_once_per_day_and_skips_locked(self):
        world = SimpleNamespace(my_slots=[slot("open"), slot("locked", locked=NOW + timedelta(days=3)), slot("shield", locked=NOW - timedelta(days=1), shielded=NOW + timedelta(hours=5))],
                                rival_slots=[slot("rival", clause_mult=1.2)])
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            self.assertEqual(exposure.snapshot(st, world, NOW, {"open": 0.02}), 3)
            self.assertEqual(exposure.snapshot(st, world, NOW), 0)
            rows = json.loads(st.get(exposure.KEY))
            self.assertEqual({r[1] for r in rows}, {"open", "shield", "rival"})
            self.assertEqual([r for r in rows if r[1] == "open"][0][5], 2.0)
            self.assertEqual([r for r in rows if r[1] == "shield"][0][6], 1)

    def test_not_before_8pm(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            self.assertEqual(exposure.snapshot(st, SimpleNamespace(my_slots=[slot("open")], rival_slots=[]), NOW.replace(hour=12)), 0)
