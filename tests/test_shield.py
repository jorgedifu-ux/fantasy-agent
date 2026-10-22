"""Blindaje: solo se gasta en quien al irse nos quita puntos de verdad."""
import unittest
from unittest import mock

from fantasy_agent import autopilot as ap
from fantasy_agent.models import Player, SquadSlot


def pl(pid, pos, avg, value=10_000_000):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=5,
                  avg_points=avg, status="ok")


def sl(p, clause=None):
    return SquadSlot(player=p, owner_team_id="me", owner_name="me",
                     clause=clause if clause is not None else p.market_value, clause_locked_until=None,
                     player_team_id="pt" + p.id)


def squad():
    gks = [pl("gk", 1, 6.0, 20_000_000)]
    defs = [pl(f"d{i}", 2, 5.0 + i * 0.1) for i in range(4)]
    mids = [pl(f"m{i}", 3, 5.0 + i * 0.1) for i in range(4)]
    fwds = [pl(f"f{i}", 4, 5.0 + i * 0.1) for i in range(2)]
    bench = pl("mayol", 3, 2.0, 1_100_000)
    return gks + defs + mids + fwds + [bench]


class ShieldTarget(unittest.TestCase):
    def test_bench_player_is_not_worth_a_shield(self):
        mine = squad()
        mayol = next(p for p in mine if p.id == "mayol")
        self.assertIsNone(ap.shield_target([sl(mayol, 1_200_000)], mine))

    def test_picks_the_starter_who_hurts_most_to_lose(self):
        mine = squad()
        weak = next(p for p in mine if p.id == "d0")
        star = next(p for p in mine if p.id == "m3")
        target = ap.shield_target([sl(weak), sl(star)], mine)
        self.assertEqual(target.player.id, "m3")

    def test_prefers_the_cheaper_clause_when_the_loss_is_similar(self):
        mine = squad()
        a = next(p for p in mine if p.id == "m2")
        b = next(p for p in mine if p.id == "m3")
        target = ap.shield_target([sl(a, int(a.market_value * 1.0)), sl(b, int(b.market_value * 1.2))], mine)
        self.assertEqual(target.player.id, "m2")

    def test_an_expensive_clause_still_gets_a_shield_when_he_is_a_key_player(self):
        mine = squad()
        gk = next(p for p in mine if p.id == "gk")
        self.assertGreaterEqual(ap.sale_loss(mine, "gk"), ap.KEY_PLAYER_LOSS)
        self.assertIsNotNone(ap.shield_target([sl(gk, int(gk.market_value * 1.19))], mine))
        self.assertIsNone(ap.shield_target([sl(gk, int(gk.market_value * 1.30))], mine))

    def test_an_expensive_clause_of_a_player_who_is_not_key_is_left_alone(self):
        mine = squad()
        d0 = next(p for p in mine if p.id == "d0")
        with mock.patch.object(ap, "KEY_PLAYER_LOSS", 5.0):      # con este listón d0 (3,3 pts) ya no es «clave»
            self.assertIsNone(ap.shield_target([sl(d0, int(d0.market_value * 1.19))], mine))

    def test_nobody_exposed_means_no_shield(self):
        self.assertIsNone(ap.shield_target([], squad()))


# ---------------------------------------------------------------------------------------------
# Protección de los que se abren: no regalar a un rival un jugador que importa (13/10/2026, Yoel Lago)
# ---------------------------------------------------------------------------------------------
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fantasy_agent import cli
from fantasy_agent.http import HttpError
from fantasy_agent.storage import Store

MADRID = timezone(timedelta(hours=2))
# domingo 18/10 21:30: la oferta diaria de hoy (20:53) ya pasó
NOW = datetime(2026, 10, 18, 21, 30, tzinfo=MADRID)


def slot_opening(p, clause, hours):
    return SquadSlot(player=p, owner_team_id="me", owner_name="me", clause=clause,
                     clause_locked_until=NOW + timedelta(hours=hours) if hours else None, player_team_id="pt" + p.id)


class DrawPending(unittest.TestCase):
    def test_a_draw_is_pending_when_it_comes_before_the_clause_opens(self):
        self.assertTrue(ap.draw_pending(NOW.replace(hour=18), NOW.replace(hour=23)))       # 20:53 llega antes de las 23:00
        self.assertFalse(ap.draw_pending(NOW, NOW + timedelta(hours=2)))                    # ya pasó y la siguiente es mañana

    def test_a_clause_that_opens_right_after_the_draw_still_counts_as_pending_before_it(self):
        self.assertTrue(ap.draw_pending(NOW.replace(hour=15), NOW.replace(hour=21, minute=2)))   # Fofana: se abre a las 21:02
        self.assertFalse(ap.draw_pending(NOW.replace(hour=21, minute=5), NOW.replace(hour=21, minute=20)))


class RaisePlan(unittest.TestCase):
    def setUp(self):
        self.mine = squad()
        self.star = next(p for p in self.mine if p.id == "m3")     # titular que importa
        self.value = self.star.market_value

    def plan(self, clause=None, hours=2, cash=25_000_000, **kw):
        s = slot_opening(self.star, clause if clause is not None else self.value, hours)
        return ap.raise_plan(s, self.mine, None, cash, NOW, **kw)

    def test_raises_to_1_20_and_pays_half_of_the_increase(self):
        inc, cost = self.plan()
        self.assertEqual(inc, round(self.value * 0.2))
        self.assertEqual(cost, inc // 2)

    def test_not_while_a_shield_is_available(self):
        self.assertIsNone(self.plan(shield_ok=True))

    def test_not_if_another_daily_offer_comes_before_it_opens(self):
        self.assertIsNone(ap.raise_plan(slot_opening(self.star, self.value, 2), self.mine, None, 25_000_000, NOW.replace(hour=19)))

    def test_not_if_the_clause_is_already_expensive(self):
        self.assertIsNone(self.plan(clause=int(self.value * 1.19)))     # Soria: si la pagan, ganamos

    def test_not_for_someone_who_does_not_matter(self):
        bench = next(p for p in self.mine if p.id == "mayol")
        self.assertIsNone(ap.raise_plan(slot_opening(bench, bench.market_value, 2), self.mine, None, 25_000_000, NOW))

    def test_not_if_it_leaves_no_cash(self):
        self.assertIsNone(self.plan(cash=2_500_000))

    def test_not_too_early(self):
        self.assertIsNone(self.plan(hours=20))

    def test_an_already_open_clause_is_protected_too(self):
        self.assertIsNotNone(self.plan(hours=0))


class FakeAPI:
    def __init__(self, quota_error=None, shields_used=0):
        self.raised = []
        self.quota_error = quota_error
        self.shields_used = shields_used

    def check_shield(self, league_id, pt):
        if self.quota_error:
            raise HttpError(400, "url", self.quota_error)

    def increase_buyout_clause(self, league_id, pt, inc):
        self.raised.append((pt, inc))

    def activity(self, league_id, page):
        if page:
            return []
        when = (NOW - timedelta(days=2)).isoformat()
        return [{"activityTypeId": 4, "user1Id": "mgr", "createdAt": when} for _ in range(self.shields_used)]

    def clear_cache(self):
        pass

    def team(self, *a):
        return {}


class ProtectExposed(unittest.TestCase):
    def run_step(self, quota_error=None, hours=2, shields_used=0, now=NOW):
        mine = squad()
        star = next(p for p in mine if p.id == "m3")
        slots = [slot_opening(star, star.market_value, hours)]
        world = SimpleNamespace(my_slots=slots, clause_freeze=None, my_cash=25_000_000, trends={}, recent_form=None,
                                standing=[SimpleNamespace(team_id="me", manager_id="mgr")], league_id="L", my_team_id="me")
        api = FakeAPI(quota_error, shields_used)
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "s.db")
            after = SimpleNamespace(player_team_id="pt" + star.id, clause=int(star.market_value * 1.2))
            with mock.patch.object(cli, "datetime", wraps=datetime) as dt, \
                    mock.patch.object(cli.models, "parse_squad", return_value=[after]), \
                    mock.patch.object(cli.service, "resolve_league", return_value=("L", "me", 22_000_000)):
                dt.now.return_value = now
                events = cli._protect_exposed(store, SimpleNamespace(), api, world)
            log = store.decisions()
            store.db.close()
            return api, events, log

    def test_raises_the_clause_of_an_exposed_player_when_the_shield_limit_is_reached(self):
        api, events, log = self.run_step('{"message":"Player team shield limit reached"}', hours=0)
        self.assertEqual(len(api.raised), 1)
        self.assertEqual(api.raised[0][1], 2_000_000)           # 20% de 10M
        self.assertEqual(log[-1]["kind"], "cláusula")
        self.assertIn("Cláusula subida", events[0])

    def test_raises_before_it_opens_when_the_two_shields_of_the_jornada_are_gone(self):
        api, events, _ = self.run_step(None, hours=2, shields_used=2)
        self.assertEqual(len(api.raised), 1)

    def test_waits_if_a_shield_is_left_before_it_opens(self):
        api, events, _ = self.run_step(None, hours=2, shields_used=1)
        self.assertEqual((api.raised, events), ([], []))

    def test_does_nothing_if_a_shield_can_still_be_used_once_open(self):
        api, events, _ = self.run_step(None, hours=0)
        self.assertEqual((api.raised, events), ([], []))

    def test_does_not_raise_if_it_was_sold_this_tick(self):
        mine = squad()
        star = next(p for p in mine if p.id == "m3")
        world = SimpleNamespace(my_slots=[slot_opening(star, star.market_value, 2)], clause_freeze=None, my_cash=25_000_000, trends={},
                                recent_form=None, standing=[SimpleNamespace(team_id="me", manager_id="mgr")], league_id="L", my_team_id="me")
        api = FakeAPI(None, 2)
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "s.db")
            store.set("sold_ids", json.dumps([star.id]))
            with mock.patch.object(cli, "datetime", wraps=datetime) as dt:
                dt.now.return_value = NOW
                self.assertEqual(cli._protect_exposed(store, SimpleNamespace(), api, world), [])
            store.db.close()
        self.assertEqual(api.raised, [])


class LiquidityReach(unittest.TestCase):
    def test_a_far_away_target_is_not_worth_selling_bench_players_for(self):
        """18/10/2026: Diomande (cláusula 69,6M) con 25M en caja y ~3M de suplentes vendibles."""
        mine = squad()
        self.assertFalse(ap.liquidity_reachable(69_560_000, 25_000_000, mine))

    def test_a_target_within_reach_is_funded_by_selling_the_bench(self):
        mine = squad()          # el único suplente vendible vale 1,1M
        self.assertTrue(ap.liquidity_reachable(26_000_000, 25_000_000, mine))
        self.assertTrue(ap.liquidity_reachable(10_000_000, 25_000_000, mine))   # ya hay caja


if __name__ == "__main__":
    unittest.main()
