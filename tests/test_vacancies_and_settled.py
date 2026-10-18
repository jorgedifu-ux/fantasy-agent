"""Recambio antes de vender y puntos definitivos (partido acabado y puntos asignados)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fantasy_agent import autopilot as ap
from fantasy_agent import pts
from fantasy_agent.models import Offer, Player, SquadSlot
from fantasy_agent.storage import Store

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def pl(pid, pos, avg, value=10_000_000):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value, points=5, avg_points=avg, status="ok")


def slot(p, hours=None, ratio=1.0):
    return SquadSlot(player=p, owner_team_id="me", owner_name="me", clause=int(p.market_value * ratio),
                     clause_locked_until=NOW + timedelta(hours=hours) if hours else None, player_team_id="pt" + p.id)


def squad_slots(hours_for=None, hours=48):
    ps = [pl("gk", 1, 6.0)] + [pl(f"d{i}", 2, 5.0) for i in range(4)] + [pl(f"m{i}", 3, 5.0) for i in range(4)] + [pl(f"f{i}", 4, 5.0) for i in range(2)]
    return [slot(p, hours if p.id == hours_for else 500) for p in ps]       # el resto, protegidos muchos días


class Vacating(unittest.TestCase):
    def test_a_starter_whose_clause_opens_soon_counts_as_a_vacancy(self):
        slots = squad_slots("d0", 20)
        self.assertEqual(ap.vacating_soon(slots, NOW), {"d0"})
        self.assertEqual(ap.vacating_soon(squad_slots("d0", 40), NOW), set())      # a más de 30 h aún caben ofertas: no se da por vendido

    def test_far_away_or_expensive_clauses_do_not(self):
        self.assertEqual(ap.vacating_soon(squad_slots("d0", 200), NOW), set())
        slots = squad_slots("d0", 20)
        slots[1] = slot(slots[1].player, 20, ratio=1.3)            # cláusula alta: si la pagan, ganamos
        self.assertEqual(ap.vacating_soon(slots, NOW), set())

    def test_a_sale_that_breaks_the_eleven_waits_for_the_replacement_within_five_days(self):
        p = pl("d0", 2, 5.0)
        offer = Offer(id="o", money=11_000_000, from_manager="LaLiga", is_system=True)
        d, why = ap.offer_decision(offer, p, loss=4.0, breaks_xi=True, hours_to_deadline=100, exposed_in=20, clause=10_000_000)
        self.assertEqual(d, "hold")
        self.assertIn("recambio", why)
        d2, _ = ap.offer_decision(offer, p, loss=4.0, breaks_xi=True, hours_to_deadline=200, exposed_in=20, clause=10_000_000)
        self.assertEqual(d2, "accept")                              # con tiempo de sobra se vende y se repone


class PremiumNeedsARealHole(unittest.TestCase):
    def test_a_high_premium_clause_is_not_paid_for_a_hole_that_may_never_open(self):
        from fantasy_agent.models import SquadSlot as SS
        mine = [pl("gk", 1, 6.0)] + [pl(f"d{i}", 2, 5.0) for i in range(4)] + [pl(f"m{i}", 3, 5.0) for i in range(4)] + [pl("f0", 4, 5.8), pl("f1", 4, 4.3)]
        star = mine[-2]
        cand = pl("fx", 4, 4.2, value=7_000_000)
        mv = ap.Move("clause", cand, int(7_000_000 * 1.18), slot=SS(player=cand, owner_team_id="r", owner_name="r", clause=int(7_000_000 * 1.18),
                                                                   clause_locked_until=None, player_team_id="ptfx"))
        without = [p for p in mine if p.id != star.id]
        # sin contar a quien se prevé vender, el hueco parece real y se pagaría la prima; contándolo, no
        naive = ap.plan_acquisitions(without, [mv], 50_000_000)
        careful = ap.plan_acquisitions(without, [mv], 50_000_000, vacated=[star])
        self.assertTrue(naive)
        self.assertEqual(careful, [])


class Settled(unittest.TestCase):
    class API:
        def __init__(self, value):
            self.value = value

        def player(self, pid):
            return {"playerStats": [{"weekNumber": 9, "totalPoints": self.value}] if self.value is not None else []}

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")
        self.kick = datetime(2026, 10, 18, 14, 0, tzinfo=timezone.utc)
        self.match = {"kickoff": self.kick, "finished": True}

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def t(self, minutes_after_kickoff):
        return self.kick.timestamp() + minutes_after_kickoff * 60

    def test_not_settled_right_after_the_final_whistle(self):
        self.assertIsNone(pts.settled_points(self.store, self.API(5), "1", 9, self.match, now=self.t(120)))

    def test_not_settled_if_the_match_is_not_finished(self):
        self.assertIsNone(pts.settled_points(self.store, self.API(5), "1", 9, {"kickoff": self.kick, "finished": False}, now=self.t(400)))

    def test_settled_only_when_the_value_has_been_stable_between_reads(self):
        api = self.API(5)
        import time
        real = time.time
        try:
            time.time = lambda: self.t(160)
            self.assertIsNone(pts.settled_points(self.store, api, "1", 9, self.match, now=self.t(160)))   # primera lectura
            time.time = lambda: self.t(170)
            self.assertIsNone(pts.settled_points(self.store, api, "1", 9, self.match, now=self.t(170)))   # solo 10 min con el mismo valor
            time.time = lambda: self.t(185)
            self.assertEqual(pts.settled_points(self.store, api, "1", 9, self.match, now=self.t(185)), 5)  # 25 min estable: definitivo
        finally:
            time.time = real

    def test_a_changing_value_restarts_the_wait(self):
        import time
        real = time.time
        try:
            time.time = lambda: self.t(160)
            pts.settled_points(self.store, self.API(5), "1", 9, self.match, now=self.t(160))
            time.time = lambda: self.t(190)
            pts.week_points(self.store, self.API(7), "1", 9)               # Fantasy corrige: 5 → 7
            time.time = lambda: self.t(195)
            self.assertIsNone(pts.settled_points(self.store, self.API(7), "1", 9, self.match, now=self.t(195)))
        finally:
            time.time = real


if __name__ == "__main__":
    unittest.main()


class NeededBids(unittest.TestCase):
    def item(self):
        from fantasy_agent.models import MarketItem
        p = pl("x", 2, 3.0, value=5_000_000)
        return MarketItem(player=p, price=5_000_000, expires=NOW + timedelta(hours=5), seller="LaLiga", bids=0, market_id="m1")

    def test_a_needed_position_is_bid_stronger_than_a_normal_target(self):
        rivals = ap.RivalPremium(median=1.10, p75=1.14)
        normal = ap.bid_amount(self.item(), 1.0, rivals)
        needed = ap.bid_amount(self.item(), 1.0, rivals, needed=True)
        self.assertGreater(needed, normal)
        self.assertEqual(needed, round(5_000_000 * 1.12))          # p75 +14%, con el techo de +12%

    def test_without_rival_data_a_needed_position_goes_to_the_cap(self):
        self.assertEqual(ap.bid_amount(self.item(), 1.0, None, needed=True), round(5_000_000 * (1 + ap.MAX_OVERBID)))
