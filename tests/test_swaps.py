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


if __name__ == "__main__":
    unittest.main()
