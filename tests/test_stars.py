"""Registro en sombra de estrellas."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fantasy_agent import stars
from fantasy_agent.models import Player, SquadSlot
from fantasy_agent.storage import Store

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def pl(pid, name, avg, value, pos=4):
    return Player(id=pid, name=name, position_id=pos, team="T", team_id="t", market_value=value, points=50, avg_points=avg, status="ok")


def item(p, price, seller="LaLiga"):
    return SimpleNamespace(player=p, price=price, seller=seller, expires=NOW + timedelta(hours=5))


def slot(p, clause, locked=None):
    return SquadSlot(player=p, owner_team_id="r", owner_name="Josinho", clause=clause, clause_locked_until=locked, player_team_id="pt" + p.id)


class Stars(unittest.TestCase):
    def test_finds_market_and_open_clause_stars_only(self):
        star, cheap, rival = pl("1", "Valles", 9.3, 55_000_000, 1), pl("2", "Barato", 3.0, 20_000_000), pl("3", "Diomande", 8.0, 90_000_000)
        locked = slot(pl("4", "Yamal", 12.7, 194_000_000), 196_000_000, NOW + timedelta(days=5))
        got = stars.candidates([item(star, 55_000_000), item(cheap, 20_000_000), item(star, 50_000_000, seller="Josinho")], [slot(rival, 90_000_000), locked],
                               {}, {"1": 4.7}, NOW, 32_000_000, 330_000_000)
        self.assertEqual([(g["kind"], g["player"]) for g in got], [("mercado", "Valles"), ("cláusula", "Diomande")])
        self.assertEqual(got[0]["form"], 4.7)
        self.assertFalse(got[0]["affordable"])
        self.assertAlmostEqual(got[0]["pct_wealth"], 16.7, places=1)

    def test_records_once_per_day(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            row = {"kind": "mercado", "player": "Valles", "price": 1}
            self.assertEqual(stars.record(st, [row]), 1)
            self.assertEqual(stars.record(st, [row]), 0)
            self.assertEqual(len(json.loads(st.get(stars.KEY))), 1)


if __name__ == "__main__":
    unittest.main()
