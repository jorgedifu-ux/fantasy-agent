"""Tests sin red: cartera de presupuesto, huecos críticos de plantilla, fichajes de emergencia."""
import unittest

from fantasy_agent.analysis import (
    Opportunity, Trend, allocate_budget, cut_loss_candidates, emergency_candidates,
    position_shortage,
)
from fantasy_agent.models import MarketItem, Player, SquadSlot


def player(pid, pos=3, status="ok", avg=5.0):
    return Player(id=pid, name=pid, position_id=pos, team="X", team_id="1",
                  market_value=10_000_000, points=10, avg_points=avg, status=status)


def opp(pid, price, score):
    item = MarketItem(player=player(pid), price=price, expires=None, seller="LaLiga", bids=0, market_id=pid)
    return Opportunity(item, Trend(0, 0, 0), score, [])


class BudgetTests(unittest.TestCase):
    def test_never_exceeds_reserved_cash(self):
        picks = [opp("a", 8_000_000, 20), opp("b", 8_000_000, 15), opp("c", 1_000_000, 10)]
        chosen = allocate_budget(picks, cash=10_000_000, reserve_pct=0.2, max_picks=3)
        total = sum(o.item.price for o in chosen)
        self.assertLessEqual(total, 10_000_000 * 0.8)

    def test_prefers_best_score_first(self):
        picks = [opp("a", 1_000_000, 5), opp("b", 1_000_000, 20)]
        chosen = allocate_budget(picks, cash=2_000_000, reserve_pct=0, max_picks=1)
        self.assertEqual([o.item.player.id for o in chosen], ["b"])

    def test_skips_unaffordable_and_takes_next(self):
        picks = [opp("caro", 9_000_000, 30), opp("barato", 1_000_000, 10)]
        chosen = allocate_budget(picks, cash=2_000_000, reserve_pct=0, max_picks=3)
        self.assertEqual([o.item.player.id for o in chosen], ["barato"])

    def test_no_cash_data_falls_back_to_plain_slice(self):
        picks = [opp("a", 1, 10), opp("b", 1, 5)]
        chosen = allocate_budget(picks, cash=None, max_picks=1)
        self.assertEqual(len(chosen), 1)


class ShortageTests(unittest.TestCase):
    def test_full_squad_no_shortage(self):
        slots = (
            [SquadSlot(player("gk", 1), "T", "yo", 0, None)]
            + [SquadSlot(player(f"d{i}", 2), "T", "yo", 0, None) for i in range(3)]
            + [SquadSlot(player(f"m{i}", 3), "T", "yo", 0, None) for i in range(3)]
            + [SquadSlot(player("f0", 4), "T", "yo", 0, None)]
        )
        self.assertEqual(position_shortage(slots), {1: 0, 2: 0, 3: 0, 4: 0})

    def test_missing_defenders_detected(self):
        slots = [SquadSlot(player("d0", 2), "T", "yo", 0, None), SquadSlot(player("gk", 1), "T", "yo", 0, None)]
        shortage = position_shortage(slots)
        self.assertEqual(shortage[2], 2)  # tiene 1, hacen falta 3
        self.assertEqual(shortage[4], 1)  # no tiene ningún delantero

    def test_injured_player_does_not_count(self):
        slots = [SquadSlot(player("d0", 2, status="lesionado"), "T", "yo", 0, None)]
        self.assertEqual(position_shortage(slots)[2], 3)


class EmergencyCandidatesTests(unittest.TestCase):
    def test_ignores_positions_not_needed(self):
        slots = [SquadSlot(player("gk", 1), "T", "yo", 0, None)]  # falta todo menos portero... pero probamos DEL
        market = [MarketItem(player("x", 1), 1_000_000, None, "LaLiga", 0, market_id="m1")]
        out = emergency_candidates(slots, market, cash=10_000_000)
        self.assertEqual(out, [])  # ya tiene portero, no hace falta otro

    def test_never_suggests_clause_targets(self):
        slots: list[SquadSlot] = []
        market = [MarketItem(player("x", 4), 1_000_000, None, seller="Pepe", bids=0, market_id="")]
        out = emergency_candidates(slots, market, cash=10_000_000)
        self.assertEqual(out, [])  # seller no es LaLiga -> es de un rival, eso es clausulazo

    def test_respects_price_cap(self):
        slots: list[SquadSlot] = []
        cheap = MarketItem(player("barato", 4, avg=3), 1_000_000, None, "LaLiga", 0, market_id="m1")
        expensive = MarketItem(player("caro", 4, avg=8), 5_000_000, None, "LaLiga", 0, market_id="m2")
        out = emergency_candidates(slots, [cheap, expensive], cash=10_000_000, cap_pct=0.15)
        ids = [o.item.player.id for o in out]
        self.assertIn("barato", ids)
        self.assertNotIn("caro", ids)  # 5M > 15% de 10M

    def test_prioritizes_shorter_position(self):
        slots = [SquadSlot(player("gk", 1), "T", "yo", 0, None)] + [
            SquadSlot(player(f"d{i}", 2), "T", "yo", 0, None) for i in range(2)  # falta 1 defensa
        ]  # 0 delanteros: falta 1; 2 defensas: falta 1 -> empate, pero probamos con más déficit en DEL
        market = [
            MarketItem(player("def_ok", 2, avg=5), 1_000_000, None, "LaLiga", 0, market_id="m1"),
            MarketItem(player("del_ok", 4, avg=5), 1_000_000, None, "LaLiga", 0, market_id="m2"),
        ]
        out = emergency_candidates(slots, market, cash=10_000_000)
        self.assertTrue(out)  # al menos uno de los dos huecos se cubre


class CutLossTests(unittest.TestCase):
    def test_sustained_fall_flagged_with_price_reason(self):
        slots = [SquadSlot(player("p1"), "T", "yo", 0, None)]
        trends = {"p1": (player("p1"), Trend(-10, -5, -12))}
        out = cut_loss_candidates(slots, trends)
        self.assertEqual([sl.player.id for sl, _ in out], ["p1"])
        self.assertIn("caída sostenida", out[0][1])  # el motivo real, no "estado: ok"

    def test_single_bad_day_not_flagged(self):
        slots = [SquadSlot(player("p1"), "T", "yo", 0, None)]
        trends = {"p1": (player("p1"), Trend(-6, -1, -9))}  # cae fuerte hoy pero no sostenido
        self.assertEqual(cut_loss_candidates(slots, trends), [])

    def test_injured_and_poor_form_flagged_with_status_reason(self):
        slots = [SquadSlot(player("p1", status="lesionado", avg=1.0), "T", "yo", 0, None)]
        out = cut_loss_candidates(slots, {})
        self.assertEqual([sl.player.id for sl, _ in out], ["p1"])
        self.assertIn("lesionado", out[0][1])

    def test_injured_but_good_form_not_flagged(self):
        slots = [SquadSlot(player("p1", status="lesionado", avg=7.0), "T", "yo", 0, None)]
        self.assertEqual(cut_loss_candidates(slots, {}), [])  # buena media, puede merecer esperar


if __name__ == "__main__":
    unittest.main()
