"""Revalorización diaria de cada plantilla."""
import unittest
from types import SimpleNamespace

from fantasy_agent import panel, reval
from fantasy_agent.models import Player, SquadSlot


def player(pid, name):
    return Player(id=pid, name=name, position_id=3, team="T", team_id="t", market_value=10_000_000, points=5, avg_points=5.0, status="ok")


def slot(p, owner):
    return SquadSlot(player=p, owner_team_id=owner, owner_name=owner, clause=p.market_value, clause_locked_until=None, player_team_id="pt" + p.id)


class FakeAPI:
    HIST = {"1": [("2026-10-16", 10.0e6), ("2026-10-17", 10.5e6), ("2026-10-18", 11.0e6)],
            "2": [("2026-10-16", 20.0e6), ("2026-10-17", 20.2e6), ("2026-10-18", 19.8e6)],
            "3": [("2026-10-16", 5.0e6), ("2026-10-17", 5.0e6), ("2026-10-18", 5.5e6)]}

    def market_value_history(self, pid):
        return [{"date": d, "marketValue": v} for d, v in self.HIST[pid]]


def world():
    mine, rival = player("1", "Hancko"), player("2", "Yamal")
    extra = player("3", "Mayol")
    return SimpleNamespace(standing=[SimpleNamespace(team_id="me", manager_id=10, manager_name="The Iberian One"),
                                     SimpleNamespace(team_id="r1", manager_id=20, manager_name="JosinhoPermanbucano")],
                           my_team_id="me", my_slots=[slot(mine, "me"), slot(extra, "me")], rival_slots=[slot(rival, "r1")])


class Reval(unittest.TestCase):
    def test_delta_and_percent_per_manager_with_todays_squad(self):
        d = reval.compute(world(), FakeAPI())
        me, he = d["managers"]["10"], d["managers"]["20"]
        self.assertAlmostEqual(me["delta"], 1.0e6)            # Hancko +0,5M y Mayol +0,5M
        self.assertAlmostEqual(he["delta"], -0.4e6)
        self.assertEqual(me["days"], [0.5e6, 1.0e6])
        self.assertEqual(he["down"][0][0], "Yamal")

    def test_section_orders_from_most_to_least_and_uses_signs_with_commas(self):
        text = panel.reval_section(reval.compute(world(), FakeAPI()))
        self.assertLess(text.index("Tú"), text.index("Josinho"))
        self.assertIn("🥇 Tú · <b>+1,0M</b>", text)
        self.assertIn("🥈 Josinho · <b>−0,4M</b> (−2,0%)", text)

    def test_refresh_only_after_0020_and_once_per_day(self):
        import tempfile
        from datetime import datetime
        from pathlib import Path
        from fantasy_agent.storage import Store
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "s.db")
            self.assertIsNone(reval.refresh(st, world(), FakeAPI(), now=datetime(2026, 10, 18, 0, 10)))
            first = reval.refresh(st, world(), FakeAPI(), now=datetime(2026, 10, 18, 0, 25))
            self.assertIsNotNone(first)
            calls = []
            api = FakeAPI()
            api.market_value_history = lambda pid: calls.append(pid) or []
            reval.refresh(st, world(), api, now=datetime(2026, 10, 18, 5, 0))
            self.assertEqual(calls, [])                         # ya calculado hoy: no vuelve a pedir nada
            st.db.close()


if __name__ == "__main__":
    unittest.main()
