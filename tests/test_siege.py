"""Tests sin red de la operación bloqueo (dejar sin portero al líder)."""
import unittest
from datetime import datetime, timedelta, timezone

from fantasy_agent import siege
from fantasy_agent.models import MarketItem, Player, SquadSlot

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
FIRST = NOW + timedelta(days=2)          # primer partido
FREEZE = FIRST - timedelta(hours=24)


def pl(pid, pos=1, value=2_000_000, status="ok", avg=3.0):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value,
                  points=10, avg_points=avg, status=status)


def slot(p, owner="t1", clause=None, locked=None, shield=None):
    return SquadSlot(player=p, owner_team_id=owner, owner_name=owner, clause=clause if clause is not None else p.market_value,
                     clause_locked_until=locked, shielded_until=shield, player_team_id=f"pt-{p.id}")


def target_squad(gks):
    """Plantilla del líder: los porteros dados + 10 de campo."""
    outfield = [slot(pl(f"d{i}", 2)) for i in range(4)] + [slot(pl(f"m{i}", 3)) for i in range(3)] + [slot(pl(f"f{i}", 4)) for i in range(3)]
    return list(gks) + outfield


def listing(p, price=None, hours=5):
    return MarketItem(player=p, price=price or p.market_value, expires=NOW + timedelta(hours=hours), seller="LaLiga",
                      bids=0, market_id=f"m-{p.id}")


def run(**kw):
    base = dict(target_slots=target_squad([slot(pl("g1"))]), other_slots=[], my_slots=[], market=[], now=NOW,
                first_match=FIRST, freeze_start=FREEZE, free_cash=50_000_000, target_cash=80_000_000, target_points=45,
                shields_used=2, jornada=10, squad_slots_free=6, my_xi_ok=True, target_name="lider", target_team_id="t1")
    base.update(kw)
    return siege.evaluate(**base)


class EvaluateTests(unittest.TestCase):
    def test_simple_case_is_viable(self):
        plan = run()
        self.assertTrue(plan.feasible, plan.reasons)
        self.assertEqual([s.kind for s in plan.steps], ["kill_clause"])

    def test_locked_goalkeeper_after_the_jornada_makes_it_impossible(self):
        gk = slot(pl("g1"), locked=FIRST + timedelta(hours=15))
        plan = run(target_slots=target_squad([gk]))
        self.assertFalse(plan.feasible)
        self.assertTrue(any("bloqueado" in r for r in plan.reasons))

    def test_all_goalkeepers_must_be_open(self):
        plan = run(target_slots=target_squad([slot(pl("g1")), slot(pl("g2"), locked=FIRST + timedelta(days=3))]))
        self.assertFalse(plan.feasible)

    def test_two_goalkeepers_are_both_taken(self):
        plan = run(target_slots=target_squad([slot(pl("g1")), slot(pl("g2"))]))
        self.assertEqual(sum(s.kind == "kill_clause" for s in plan.steps), 2)

    def test_open_goalkeeper_of_another_rival_must_be_taken_too(self):
        plan = run(other_slots=[slot(pl("other", value=5_000_000), owner="t2")])
        self.assertIn("block_clause", [s.kind for s in plan.steps])

    def test_other_rivals_goalkeeper_he_cannot_afford_is_ignored(self):
        plan = run(other_slots=[slot(pl("star", value=60_000_000), owner="t2")], target_cash=20_000_000)
        self.assertNotIn("block_clause", [s.kind for s in plan.steps])

    def test_locked_goalkeeper_of_another_rival_is_ignored(self):
        plan = run(other_slots=[slot(pl("other"), owner="t2", locked=FIRST + timedelta(days=2))])
        self.assertNotIn("block_clause", [s.kind for s in plan.steps])

    def test_market_goalkeepers_are_bid_on_with_a_premium(self):
        it = listing(pl("mk", value=1_000_000))
        plan = run(market=[it])
        [step] = [s for s in plan.steps if s.kind == "block_bid"]
        self.assertEqual(step.cost, round(1_000_000 * siege.MARKET_BLOCK_FACTOR))
        self.assertEqual(step.when, "pre")

    def test_listing_that_resolves_after_kickoff_is_irrelevant(self):
        plan = run(market=[listing(pl("late"), hours=24 * 3)])
        self.assertNotIn("block_bid", [s.kind for s in plan.steps])

    def test_my_own_open_goalkeeper_blocks_the_plan(self):
        plan = run(my_slots=[slot(pl("mygk", value=5_000_000), owner="me")])
        self.assertFalse(plan.feasible)
        self.assertTrue(any("tu portero" in r for r in plan.reasons))

    def test_my_locked_goalkeeper_is_fine(self):
        plan = run(my_slots=[slot(pl("mygk"), owner="me", locked=FIRST + timedelta(days=5))])
        self.assertTrue(plan.feasible, plan.reasons)

    def test_available_shields_lower_the_certainty(self):
        self.assertLess(run(shields_used=0).certainty, run(shields_used=2).certainty)

    def test_not_enough_cash(self):
        plan = run(free_cash=500_000)
        self.assertFalse(plan.feasible)
        self.assertTrue(any("faltan" in r for r in plan.reasons))

    def test_spending_cap_depends_on_the_stage_of_the_league(self):
        gk = slot(pl("g1", value=30_000_000))
        early = run(target_slots=target_squad([gk]), free_cash=50_000_000, jornada=3)
        late = run(target_slots=target_squad([gk]), free_cash=50_000_000, jornada=34)
        self.assertGreater(late.max_outlay, early.max_outlay)

    def test_not_worth_it_when_the_leader_scores_little(self):
        plan = run(target_slots=target_squad([slot(pl("g1", value=20_000_000))]), target_points=5, free_cash=200_000_000)
        self.assertFalse(plan.feasible)
        self.assertTrue(any("no compensa" in r for r in plan.reasons))

    def test_frozen_clauses(self):
        plan = run(now=FREEZE + timedelta(minutes=1))
        self.assertFalse(plan.feasible)

    def test_incomplete_own_squad_goes_first(self):
        self.assertFalse(run(my_xi_ok=False).feasible)

    def test_already_without_goalkeeper_and_cannot_replace(self):
        plan = run(target_slots=target_squad([]))
        self.assertFalse(plan.feasible)
        self.assertTrue(any("ya está sin portero" in r for r in plan.reasons))

    def test_not_enough_squad_slots(self):
        plan = run(target_slots=target_squad([slot(pl("g1")), slot(pl("g2"))]), squad_slots_free=1)
        self.assertTrue(any("plantilla" in r for r in plan.reasons))

    def test_already_placed_bids_cost_nothing_more(self):
        it = listing(pl("mk", value=1_000_000))
        it.my_bid = 1_400_000
        plan = run(market=[it])
        [step] = [s for s in plan.steps if s.kind == "block_bid"]
        self.assertEqual(step.cost, 0)


class StageTests(unittest.TestCase):
    def test_stage_factor(self):
        self.assertLess(siege.stage_factor(2), siege.stage_factor(15))
        self.assertLess(siege.stage_factor(15), siege.stage_factor(33))


class OffersHoldTests(unittest.TestCase):
    def test_siege_players_are_not_sold_before_the_jornada(self):
        from fantasy_agent import autopilot as ap
        from fantasy_agent.models import Offer
        offer = Offer(id="o", money=50_000_000, from_manager="LaLiga", is_system=True)
        self.assertEqual(ap.offer_decision(offer, pl("g", value=1_000_000), loss=0, no_sell=True)[0], "hold")


if __name__ == "__main__":
    unittest.main()
