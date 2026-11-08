"""Modo estrella: cuándo compensa fichar a una estrella (opción B, 8/11/2026)."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from fantasy_agent import autopilot as ap
from fantasy_agent import starmode
from fantasy_agent.models import Offer, Player, SquadSlot

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


def pl(pid, pos, avg, value, status="ok"):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=int(avg * 10), avg_points=avg, status=status)


def squad():
    """Once completo (1-4-4-2) de jugadores de 5-6 pts y 20-40M, más un banquillo flojo."""
    gk = [pl("gk", 1, 5.0, 12_000_000), pl("gk2", 1, 1.0, 1_000_000)]
    d = [pl(f"d{i}", 2, 5.0 + i * 0.2, 30_000_000) for i in range(4)] + [pl("d_b", 2, 2.5, 2_000_000)]
    m = [pl(f"m{i}", 3, 5.0 + i * 0.2, 30_000_000) for i in range(4)] + [pl("m_b", 3, 2.5, 2_000_000)]
    f = [pl(f"f{i}", 4, 5.0 + i * 0.2, 30_000_000) for i in range(2)] + [pl("f_b", 4, 2.5, 2_000_000)]
    return gk + d + m + f


def star_slot(pid="star", avg=13.0, value=100_000_000, clause_mult=1.0, locked=None, shielded=None):
    p = pl(pid, 4, avg, value)
    return SquadSlot(player=p, owner_team_id="r", owner_name="rival", clause=int(value * clause_mult), clause_locked_until=locked,
                     shielded_until=shielded, player_team_id="pt" + pid)


def run(mine=None, slots=None, cash=80_000_000, wealth=None, hours=300, weeks=25, trends=None):
    mine = mine or squad()
    wealth = wealth or cash + sum(p.market_value for p in mine)
    return starmode.plan(mine, slots if slots is not None else [star_slot()], trends or {}, None, cash, wealth, NOW, hours, weeks)


class StarPlan(unittest.TestCase):
    def test_a_real_star_is_worth_it_and_sells_the_least_useful_first(self):
        plan = run()
        self.assertIsNotNone(plan)
        self.assertEqual(plan.player_id, "star")
        self.assertGreaterEqual(plan.gain, starmode.STAR_MIN_GAIN)
        sold = {i for i, _ in plan.sells}
        self.assertNotIn("gk", sold)
        self.assertTrue(sold)

    def test_no_sales_needed_when_there_is_cash(self):
        plan = run(cash=150_000_000)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.sells, [])

    def test_a_mediocre_player_is_not_a_star(self):
        self.assertIsNone(run(slots=[star_slot(avg=7.0)]))

    def test_too_close_to_the_next_matchday_or_too_late_in_the_season(self):
        self.assertIsNone(run(hours=48))
        self.assertIsNone(run(weeks=10))

    def test_blocked_shielded_or_expensive_clause_is_skipped(self):
        from datetime import timedelta
        self.assertIsNone(run(slots=[star_slot(locked=NOW + timedelta(days=2))]))
        self.assertIsNone(run(slots=[star_slot(shielded=NOW + timedelta(hours=5))]))
        self.assertIsNone(run(slots=[star_slot(clause_mult=1.3)]))

    def test_falling_player_is_skipped(self):
        tr = {"star": (None, SimpleNamespace(d1=-1.0, d3=-3.0, d7=-5.0))}
        self.assertIsNone(run(trends=tr))

    def test_price_above_the_share_of_wealth_is_skipped(self):
        self.assertIsNone(run(slots=[star_slot(value=400_000_000)]))

    def test_no_plan_if_the_eleven_would_be_incomplete(self):
        # sin bancos: vender lo necesario deja huecos sin cubrir
        mine = [pl("gk", 1, 5.0, 12_000_000)] + [pl(f"d{i}", 2, 5.0, 40_000_000) for i in range(4)] + [pl(f"m{i}", 3, 5.0, 40_000_000) for i in range(4)] + [pl(f"f{i}", 4, 5.0, 40_000_000) for i in range(2)]
        self.assertIsNone(run(mine=mine, slots=[star_slot(value=160_000_000)], cash=5_000_000))


class StarSale(unittest.TestCase):
    def test_players_of_the_plan_are_sold_at_a_small_discount(self):
        p = pl("x", 3, 5.0, 30_000_000)
        mk = lambda r: Offer(id="o", money=round(30_000_000 * r), from_manager="LaLiga", is_system=True)
        self.assertEqual(ap.offer_decision(mk(0.98), p, loss=2.0, star_sale=True, cost_basis=35_000_000)[0], "accept")
        self.assertEqual(ap.offer_decision(mk(0.95), p, loss=2.0, star_sale=True)[0], "hold")
        self.assertEqual(ap.offer_decision(mk(0.98), p, loss=2.0)[0], "hold")


if __name__ == "__main__":
    unittest.main()


from fantasy_agent.models import MarketItem


def item(pid="mstar", avg=11.0, value=60_000_000, price=None, seller="LaLiga", status="ok", my_bid=0):
    p = pl(pid, 4, avg, value, status)
    return MarketItem(player=p, price=price or value, expires=NOW, seller=seller, bids=0, market_id="m" + pid, my_bid=my_bid)


def mplan(items=None, budget=70_000_000, credit=0, rivals=(), p75=None, hours=300, weeks=25, mine=None, max_squad=23, trends=None):
    mine = mine or squad()
    return starmode.market_plan(mine, items if items is not None else [item()], trends or {}, None, budget, credit, 400_000_000, list(rivals), p75, hours, weeks, max_squad)


class MarketStar(unittest.TestCase):
    def test_bids_one_percent_over_the_floor_if_no_rival_can_pay(self):
        bid, able = starmode.star_bid(60_000_000, [20_000_000, 35_000_000], 1.10, 60_000_000)
        self.assertEqual((bid, able), (round(60_000_000 * 1.01), 0))

    def test_bids_the_typical_premium_if_a_rival_can_pay(self):
        bid, able = starmode.star_bid(60_000_000, [200_000_000], 1.09, 60_000_000)
        self.assertEqual(able, 1)
        self.assertAlmostEqual(bid / 60_000_000, 1.09, places=2)

    def test_the_premium_is_capped_and_never_below_the_minimum(self):
        self.assertLessEqual(starmode.star_bid(60_000_000, [500_000_000], 1.60, 60_000_000)[0], 60_000_000 * 1.15 + 1)
        self.assertGreaterEqual(starmode.star_bid(60_000_000, [500_000_000], 1.001, 60_000_000)[0], 60_000_000 * 1.03 - 1)

    def test_if_the_richest_rival_barely_reaches_the_floor_we_just_beat_his_cash(self):
        bid, able = starmode.star_bid(60_000_000, [61_000_000], 1.12, 60_000_000)
        self.assertEqual(able, 1)
        self.assertLess(bid, 60_000_000 * 1.03)
        self.assertGreater(bid, 61_000_000)

    def test_a_market_star_is_planned_with_cash_and_credit_and_no_sales(self):
        plan = mplan(budget=40_000_000, credit=30_000_000)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.item.player.id, "mstar")
        self.assertGreater(plan.uses_credit, 0)
        self.assertGreaterEqual(plan.gain, starmode.STAR_MIN_GAIN)

    def test_not_if_it_does_not_fit_in_cash_plus_credit(self):
        self.assertIsNone(mplan(budget=10_000_000, credit=20_000_000))

    def test_not_other_sellers_injured_mediocre_or_already_bid(self):
        self.assertIsNone(mplan(items=[item(seller="Pep")]))
        self.assertIsNone(mplan(items=[item(status="injured")]))
        self.assertIsNone(mplan(items=[item(avg=6.0)]))
        self.assertIsNone(mplan(items=[item(my_bid=1)]))

    def test_not_too_close_to_a_matchday_or_with_a_full_squad(self):
        self.assertIsNone(mplan(hours=30))
        self.assertIsNone(mplan(mine=squad(), max_squad=len(squad())))

    def test_a_big_premium_is_not_paid_for_a_small_gain(self):
        # con un rival rico la puja sube; si la ganancia de puntos no compensa la prima, no se puja
        plan = mplan(items=[item(avg=9.5, value=60_000_000)], rivals=[300_000_000], p75=1.15, weeks=16)
        if plan is not None:
            self.assertGreaterEqual(plan.gain * 0.3 * 16, (plan.bid - 60_000_000) / 1e6)
