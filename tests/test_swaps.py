"""Permutas (vender A para fichar B), cláusulas con más ratio si falta una posición, y fichaje de emergencia sin caídas."""
import unittest
from datetime import datetime, timezone

from fantasy_agent import analysis, autopilot as ap
from fantasy_agent.models import Player, SquadSlot

NOW = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)


def pl(pid, pos, avg=4.0, value=10_000_000, status="ok"):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=int(avg * 7), avg_points=avg, status=status)


def slot_of(p):
    return SquadSlot(player=p, owner_team_id="me", owner_name="me", clause=p.market_value, clause_locked_until=None, player_team_id="pt" + p.id)


def squad():
    """Once completo 4-3-3 de media 5 + un suplente flojo y barato + un suplente que sube."""
    xi = [pl("gk", 1, 5, 5_000_000)] + [pl(f"d{i}", 2, 5) for i in range(4)] + [pl(f"m{i}", 3, 5) for i in range(3)] + [pl(f"f{i}", 4, 5) for i in range(3)]
    return xi + [pl("weak", 3, 1.0, 12_000_000), pl("riser", 3, 1.0, 12_000_000)]


class SwapTests(unittest.TestCase):
    def setUp(self):
        self.slots = [slot_of(p) for p in squad()]
        self.trends = {p.id: analysis.Trend(0, 0, 0) for p in squad()}
        self.trends["riser"] = analysis.Trend(3.0, 9.0, 15.0)            # sube con fuerza
        star = pl("star", 3, 9.0, 20_000_000)                            # mejora el once y cuesta más de lo que hay libre
        self.buy = ap.Move("clause", star, 20_000_000, drift=0.15)

    def test_sells_the_bench_player_that_neither_scores_nor_rises(self):
        swaps = ap.swap_candidates(self.slots, [self.buy], self.trends, None, free_cash=9_000_000)
        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0].sell.id, "weak")                        # no el que sube, ni un titular
        self.assertGreaterEqual(swaps[0].edge_m, ap.SWAP_MARGIN_M)

    def test_never_swaps_when_the_money_is_already_there(self):
        self.assertEqual(ap.swap_candidates(self.slots, [self.buy], self.trends, None, free_cash=25_000_000), [])

    def test_protected_players_and_the_only_keeper_stay(self):
        swaps = ap.swap_candidates(self.slots, [self.buy], self.trends, None, 9_000_000, protected_ids=frozenset({"weak", "riser"}))
        self.assertTrue(all(s.sell.id not in ("weak", "riser") for s in swaps))
        # vender al único portero dejaría el once sin completar: jamás sale por una permuta
        self.assertTrue(all(s.sell.id != "gk" for s in swaps))

    def test_a_marginal_upgrade_is_not_worth_it(self):
        meh = ap.Move("clause", pl("meh", 3, 1.2, 20_000_000), 20_000_000, drift=0.0)
        self.assertEqual(ap.swap_candidates(self.slots, [meh], self.trends, None, 9_000_000), [])


class ShortRatio(unittest.TestCase):
    def test_a_keeper_clause_slightly_over_1_2x_is_allowed_only_when_the_position_is_short(self):
        ryan = pl("ryan", 1, 6.4, 25_000_000)
        sl = SquadSlot(player=ryan, owner_team_id="pep", owner_name="pep", clause=30_450_000, clause_locked_until=None, player_team_id="p")   # 1,22×
        self.assertEqual(ap.clause_moves([sl], NOW), [])
        self.assertEqual(len(ap.clause_moves([sl], NOW, short_positions=frozenset({1}))), 1)
        way_over = SquadSlot(player=ryan, owner_team_id="pep", owner_name="pep", clause=40_000_000, clause_locked_until=None, player_team_id="p")
        self.assertEqual(ap.clause_moves([way_over], NOW, short_positions=frozenset({1})), [])


class SwapSafety(unittest.TestCase):
    def setUp(self):
        self.slots = [slot_of(p) for p in squad()]
        self.mine = [sl.player for sl in self.slots]
        self.star = pl("star", 3, 9.0, 20_000_000)
        self.sw = ap.Swap(sell=self.mine[-2], buy=ap.Move("clause", self.star, 20_000_000, drift=0.15), edge_m=3.0, keep_m=0.4, buy_net_m=3.4)

    def test_ok_when_everything_holds(self):
        self.assertEqual(ap.swap_is_safe(self.sw, self.mine, 9_000_000, 12_000_000, 80.0), (True, "ok"))

    def test_a_market_bid_is_never_executed_as_a_swap(self):
        bid = ap.Swap(sell=self.sw.sell, buy=ap.Move("bid", self.star, 20_000_000, drift=0.15), edge_m=6.0, keep_m=0.4, buy_net_m=6.4)
        ok, why = ap.swap_is_safe(bid, self.mine, 9_000_000, 12_000_000, 80.0)
        self.assertFalse(ok)
        self.assertIn("puja de mercado", why)

    def test_each_condition_blocks(self):
        small = ap.Swap(self.sw.sell, self.sw.buy, 1.0, 0.4, 1.4)
        self.assertFalse(ap.swap_is_safe(small, self.mine, 9_000_000, 12_000_000, 80.0)[0])             # ventaja baja
        self.assertFalse(ap.swap_is_safe(self.sw, self.mine, 9_000_000, 12_000_000, 20.0)[0])           # jornada cerca
        self.assertFalse(ap.swap_is_safe(self.sw, self.mine, 9_000_000, 11_000_000, 80.0)[0])           # oferta <1,00×
        self.assertFalse(ap.swap_is_safe(self.sw, self.mine, 1_000_000, 12_000_000, 80.0)[0])           # no alcanza el dinero

    def test_the_hancko_case_a_swap_that_leaves_no_legal_eleven_is_refused(self):
        # solo 3 defensas: vender uno por un delantero deja el once sin completar (lo que pasó a las 21:16 con la propuesta de Hancko)
        mine = [p for p in self.mine if p.position_id != 2] + [pl(f"d{i}", 2, 5) for i in range(3)]
        sw = ap.Swap(sell=mine[-1], buy=self.sw.buy, edge_m=5.0, keep_m=0.4, buy_net_m=5.4)
        ok, why = ap.swap_is_safe(sw, mine, 30_000_000, 12_000_000, 80.0)
        self.assertFalse(ok)
        self.assertIn("once legal", why)


class CreditOnlyForBids(unittest.TestCase):
    def setUp(self):
        def mv(kind, pid, cost, score):
            it = None
            if kind == "invest":
                from fantasy_agent.models import MarketItem
                it = MarketItem(player=pl(pid, 3, 5.0, cost), price=cost, expires=None, seller="LaLiga", bids=0, market_id="m" + pid)
            return ap.Move(kind, pl(pid, 3, 5.0, cost), cost, item=it, score=score)
        self.clause = mv("invest_clause", "c", 15_000_000, 9)
        self.bid = mv("invest", "b", 15_000_000, 5)

    def test_credit_never_pays_a_clause(self):
        plan = ap.plan_investments_with_credit([self.clause, self.bid], cash_budget=0, credit=50_000_000, slots=3)
        self.assertEqual([m.kind for m in plan], ["invest"])              # con solo crédito: únicamente la puja

    def test_cash_can_pay_both_and_credit_adds_only_bids(self):
        plan = ap.plan_investments_with_credit([self.clause, self.bid], cash_budget=100_000_000, credit=50_000_000, slots=3)
        self.assertEqual(sorted(m.kind for m in plan), ["invest", "invest_clause"])


if __name__ == "__main__":
    unittest.main()
