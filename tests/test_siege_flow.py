"""Prueba del flujo de ejecución del bloqueo (cli._siege_go / _siege_tick) con una API falsa."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fantasy_agent import cli, siege
from fantasy_agent.models import Player, SquadSlot
from fantasy_agent.storage import Store
from fantasy_agent.service import Outlook

NOW = datetime.now(timezone.utc)
FIRST = NOW + timedelta(hours=24, minutes=4)
FREEZE = FIRST - timedelta(hours=24)       # empieza en 4 min


def gk(pid, value=2_000_000):
    return Player(id=pid, name=pid, position_id=1, team="T", team_id="t", market_value=value, points=5, avg_points=3.0, status="ok")


def make_plan(feasible=True):
    p = gk("g1")
    sl = SquadSlot(player=p, owner_team_id="t1", owner_name="lider", clause=2_000_000, clause_locked_until=None, player_team_id="pt-g1")
    plan = siege.SiegePlan(target_name="lider", target_team_id="t1", exec_at=FREEZE - siege.EXEC_MARGIN, feasible=feasible,
                           steps=[siege.Step("kill_clause", p, 2_000_000, slot=sl, note="cláusula de lider")], outlay=2_000_000,
                           certainty=0.8)
    if not feasible:
        plan.reasons = ["ya no compensa"]
    return plan


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.live_clause = 2_000_000  # lo que la API dice que vale la cláusula al releerla

    def team_fresh(self, league, team_id):
        return {"players": [{"playerMaster": {"id": "g1", "nickname": "g1", "positionId": 1, "marketValue": 2_000_000},
                             "playerTeamId": "pt-g1", "buyoutClause": self.live_clause}]}

    def clear_cache(self): pass
    def pay_buyout_clause(self, league, ptid, amount): self.calls.append(("clause", ptid, amount))
    def bid(self, league, market, money): self.calls.append(("bid", market, money))
    def team(self, league, team_id): return {"players": []}


def world():
    return SimpleNamespace(outlook=Outlook(next_first=FIRST), clause_freeze=(FREEZE, FIRST), league_id="L")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")
        self.api = FakeAPI()
        key = FIRST.isoformat()
        self.store.set("siege_state", json.dumps({"jornada": key, "armed": True}))
        sleeps = patch("fantasy_agent.cli.time.sleep")
        self.sleep = sleeps.start()
        self.addCleanup(sleeps.stop)

    def go(self, plan):
        with patch.object(cli, "_world", return_value=world()), patch.object(cli, "_siege_plan", return_value=plan):
            return cli._siege_go(self.store, None, self.api, world())

    def test_executes_the_clause_when_still_viable(self):
        events = self.go(make_plan())
        self.assertEqual(self.api.calls, [("clause", "pt-g1", 2_000_000)])
        self.assertIn("g1", cli._siege_ids(self.store))
        self.assertTrue(any("✅" in e for e in events))
        self.sleep.assert_called()  # espera hasta el segundo exacto

    def test_cancels_if_no_longer_viable(self):
        events = self.go(make_plan(feasible=False))
        self.assertEqual(self.api.calls, [])
        self.assertTrue(any("cancelada" in e for e in events))

    def test_runs_only_once_per_jornada(self):
        self.go(make_plan())
        self.api.calls.clear()
        self.assertEqual(self.go(make_plan()), [])
        self.assertEqual(self.api.calls, [])

    def test_does_nothing_if_not_armed(self):
        self.store.set("siege_state", json.dumps({"jornada": FIRST.isoformat(), "armed": False}))
        self.assertEqual(self.go(make_plan()), [])
        self.assertEqual(self.api.calls, [])

    def test_does_nothing_if_the_moment_is_far(self):
        far = SimpleNamespace(outlook=Outlook(next_first=FIRST + timedelta(hours=10)),
                              clause_freeze=(FREEZE + timedelta(hours=10), FIRST + timedelta(hours=10)), league_id="L")
        with patch.object(cli, "_world", return_value=far), patch.object(cli, "_siege_plan", return_value=make_plan()):
            self.store.set("siege_state", json.dumps({"jornada": (FIRST + timedelta(hours=10)).isoformat(), "armed": True}))
            self.assertEqual(cli._siege_go(self.store, None, self.api, far), [])
        self.assertEqual(self.api.calls, [])

    def test_does_not_pay_if_the_clause_rose(self):
        self.api.live_clause = 2_400_000
        events = self.go(make_plan())
        self.assertEqual(self.api.calls, [])
        self.assertTrue(any("ha subido" in e for e in events))

    def test_failed_kill_stops_the_rest(self):
        plan = make_plan()
        other = gk("g2")
        plan.steps.append(siege.Step("block_clause", other, 1_000_000,
                                     slot=SquadSlot(player=other, owner_team_id="t2", owner_name="x", clause=1_000_000,
                                                    clause_locked_until=None, player_team_id="pt-g2")))
        self.api.pay_buyout_clause = lambda *a: (_ for _ in ()).throw(RuntimeError("blindado"))
        events = self.go(plan)
        self.assertTrue(any("Paro aquí" in e for e in events))


if __name__ == "__main__":
    unittest.main()
