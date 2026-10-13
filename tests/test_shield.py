"""Blindaje: solo se gasta en quien al irse nos quita puntos de verdad."""
import unittest

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

    def test_nobody_exposed_means_no_shield(self):
        self.assertIsNone(ap.shield_target([], squad()))


if __name__ == "__main__":
    unittest.main()
