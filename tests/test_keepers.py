"""Portero de reserva protegido, y limpieza de pujas que ya no tienen sentido."""
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fantasy_agent import autopilot as ap
from fantasy_agent import cli
from fantasy_agent.models import MarketItem, Offer, Player, SquadSlot
from fantasy_agent.storage import Store

NOW = datetime(2026, 10, 10, 22, 0, tzinfo=timezone.utc)
FREEZE = (NOW + timedelta(days=5), NOW + timedelta(days=6))   # congelación de la próxima jornada


def gk(pid, avg=1.0, value=1_000_000, status="ok"):
    return Player(id=pid, name=pid, position_id=1, team="T", team_id="t", market_value=value, points=5, avg_points=avg, status=status)


def slot(p, locked=None, clause=None, owner="me"):
    return SquadSlot(player=p, owner_team_id=owner, owner_name=owner, clause=clause if clause is not None else p.market_value,
                     clause_locked_until=locked, player_team_id="pt" + p.id)


def item(p, price, seller="LaLiga"):
    return MarketItem(player=p, price=price, expires=NOW + timedelta(hours=20), seller=seller, bids=0, market_id="m" + p.id)


class KeeperCover(unittest.TestCase):
    def test_soria_alone_is_exposed(self):
        soria = slot(gk("soria", 7.5, 38_000_000), locked=NOW + timedelta(days=1))   # se abre antes de la congelación
        self.assertEqual(ap.keeper_cover([soria], [], FREEZE[0]), (1, 0))

    def test_recent_purchase_is_protected_until_the_freeze(self):
        backup = slot(gk("b"), locked=NOW + timedelta(days=14))
        soria = slot(gk("soria"), locked=NOW + timedelta(days=1))
        self.assertEqual(ap.keeper_cover([soria, backup], [], FREEZE[0]), (2, 1))

    def test_injured_keeper_does_not_count_and_a_live_bid_does(self):
        hurt = slot(gk("h", status="injured"), locked=NOW + timedelta(days=14))
        self.assertEqual(ap.keeper_cover([hurt], [], FREEZE[0]), (0, 0))
        self.assertEqual(ap.keeper_cover([hurt], [gk("bid")], FREEZE[0]), (1, 1))


class ExpensiveProtectedKeeper(unittest.TestCase):
    """Herrero (21M, golpe al líder) cuenta como portero protegido. Reserva barata SOLO si (1) nos quedamos con un único portero Y (2) su protección
    está a punto de acabar (o no hay ninguno protegido). Con dos porteros no se compra (decisión del usuario: 1 y 2, no 1 o 2)."""
    def setUp(self):
        self.soria = slot(gk("soria", 7.5, 38_000_000), locked=NOW - timedelta(days=2))             # ya clausulable
        self.market = [item(gk("mk", 0.0, 590_000), 610_000)]

    def herrero(self, locked_h):
        return slot(gk("herrero", 5.4, 21_000_000), locked=NOW + timedelta(hours=locked_h))

    def move(self, slots, market=None, incoming=(), freeze=FREEZE, budget=30_000_000):
        return ap.backup_keeper_move(slots, list(incoming), self.market if market is None else market, [], NOW, freeze, budget)

    def test_with_soria_and_herrero_nothing_is_bought_even_if_herrero_is_about_to_fall(self):
        for hours in (14 * 24, 60, 40, 5):
            self.assertIsNone(self.move([self.soria, self.herrero(hours)]), hours)

    def test_soria_gone_and_herrero_protected_for_long_nothing_is_bought(self):
        self.assertIsNone(self.move([self.herrero(14 * 24)]))
        soon = (NOW + timedelta(hours=30), NOW + timedelta(hours=54))
        self.assertIsNone(self.move([self.herrero(60)], freeze=soon))       # protegido en la congelación y a 60 h (>48) de que acabe

    def test_soria_gone_and_herrero_about_to_fall_buys_the_cheap_reserve(self):
        self.assertEqual(self.move([self.herrero(40)]).player.id, "mk")      # a 40 h (<48): busca un portero de ≤0,8M
        pricey = [item(gk("pricey", 3.0, 1_200_000), 1_200_000)]
        self.assertIsNone(self.move([self.herrero(40)], market=pricey))      # 1,2M: aún se espera
        self.assertEqual(self.move([self.herrero(20)], market=pricey).player.id, "pricey")   # en las últimas 24 h, hasta 1,5M
        self.assertIsNone(self.move([self.herrero(20)], market=[item(gk("big", 4.0, 3_000_000), 3_000_000)]))   # nunca 3M

    def test_if_the_planner_is_already_buying_a_starter_keeper_no_reserve(self):
        self.assertIsNone(self.move([self.herrero(20)], incoming=[gk("starter", 8.0, 40_000_000)]))

    def test_cover_counts_any_protected_keeper(self):
        self.assertEqual(ap.keeper_cover([self.soria, self.herrero(14 * 24)], [], FREEZE[0]), (2, 1))


def dfn(pid, avg=3.0, value=800_000, status="ok"):
    return Player(id=pid, name=pid, position_id=2, team="T", team_id="t", market_value=value, points=int(avg * 7), avg_points=avg, status=status)


class DepthDefender(unittest.TestCase):
    def setUp(self):
        self.slots = [slot(dfn(f"d{i}", 6.0, 15_000_000)) for i in range(3)]

    def move(self, market=(), rivals=(), slots=None, incoming=(), budget=30_000_000, freeze=FREEZE):
        return ap.depth_defender_move(slots or self.slots, list(incoming), list(market), list(rivals), NOW, freeze, budget)

    def test_buys_the_cheapest_fourth_defender(self):
        cheap = MarketItem(player=dfn("luiz", 2.0, 880_000), price=880_000, expires=NOW + timedelta(hours=20), seller="LaLiga", bids=0, market_id="m1")
        pricey = MarketItem(player=dfn("big", 6.0, 19_000_000), price=19_000_000, expires=NOW + timedelta(hours=20), seller="LaLiga", bids=0, market_id="m2")
        self.assertEqual(self.move(market=[cheap, pricey]).player.id, "luiz")

    def test_patient_far_from_the_freeze_and_needs_some_level(self):
        mid = MarketItem(player=dfn("mid", 3.0, 1_200_000), price=1_200_000, expires=NOW + timedelta(hours=20), seller="LaLiga", bids=0, market_id="m1")
        junk = MarketItem(player=dfn("junk", 0.2, 500_000), price=500_000, expires=NOW + timedelta(hours=20), seller="LaLiga", bids=0, market_id="m2")
        self.assertIsNone(self.move(market=[mid, junk]))                                                         # 1,2M > 1M y quedan 5 días; el otro no juega
        near = (NOW + timedelta(hours=30), NOW + timedelta(hours=54))
        self.assertEqual(self.move(market=[mid, junk], freeze=near).player.id, "mid")

    def test_not_needed_with_four_or_with_none(self):
        four = self.slots + [slot(dfn("d4"))]
        self.assertIsNone(self.move(slots=four))
        self.assertIsNone(self.move(slots=[]))                       # sin defensas manda el planificador normal
        self.assertIsNone(self.move(incoming=[dfn("coming")]))       # una puja viva ya cuenta


class SurplusKeeper(unittest.TestCase):
    """Solo puede jugar un portero: uno caro de banquillo que se frena o cae se suelta; uno barato o que sube se queda como reserva."""
    def test_who_is_kept_as_a_needed_reserve(self):
        herrero = gk("herrero", 5.4, 21_000_000)
        cheap = gk("cheap", 1.0, 600_000)
        self.assertTrue(ap.hold_as_reserve(herrero, 2, 0.5, falling=False))        # sube: se queda
        self.assertFalse(ap.hold_as_reserve(herrero, 2, 0.5, falling=True))        # caro y cayendo: se suelta
        self.assertTrue(ap.hold_as_reserve(cheap, 2, 0.1, falling=True))           # barato: se queda aunque baje
        self.assertFalse(ap.hold_as_reserve(herrero, 3, 0.5, falling=False))       # con 3 porteros sobra uno
        self.assertFalse(ap.hold_as_reserve(herrero, 2, 5.0, falling=False))       # el titular lo decide la regla de "clave"

    def test_a_falling_expensive_keeper_is_sold_at_value(self):
        herrero = gk("herrero", 5.4, 21_000_000)
        o = Offer(id="o", money=21_000_000, from_manager="LaLiga", is_system=True)
        d, _ = ap.offer_decision(o, herrero, loss=0.5, trend_d7=8.0, trend_d3=0.5, trend_d1=0.0, hours_to_deadline=100,
                                 reserve_keeper=ap.hold_as_reserve(herrero, 2, 0.5, True), cost_basis=21_190_000)
        self.assertEqual(d, "accept")                                              # salida al frenarse: a su valor, sin mirar lo pagado


class MakingRoom(unittest.TestCase):
    def mv(self, pid):
        return ap.Move("bid", gk(pid), 1)

    def test_keeper_goes_first_and_drops_the_last_planned_when_full(self):
        keeper = self.mv("k")
        plan, missing = ap.add_reserve_keeper([self.mv("a"), self.mv("b")], keeper, n_mine=14, max_squad=16)
        self.assertEqual(([m.player.id for m in plan], missing), (["k", "a"], 1))   # Berrocal fuera hasta que haya plaza

    def test_no_change_when_there_is_room_or_no_keeper(self):
        keeper = self.mv("k")
        plan, missing = ap.add_reserve_keeper([self.mv("a")], keeper, n_mine=13, max_squad=16)
        self.assertEqual(([m.player.id for m in plan], missing), (["k", "a"], 0))
        self.assertEqual(ap.add_reserve_keeper([self.mv("a")], None, 14, 16)[1], 0)

    def test_full_squad_with_empty_plan_needs_a_slot(self):
        plan, missing = ap.add_reserve_keeper([], self.mv("k"), n_mine=16, max_squad=16)
        self.assertEqual((plan, missing), ([], 1))

    def test_free_slot_sells_a_cheap_riser_but_never_below_cost(self):
        p = Player(id="m", name="Mayol", position_id=3, team="T", team_id="t", market_value=1_200_000, points=14, avg_points=3.5, status="ok")
        o = Offer(id="o", money=1_200_000, from_manager="LaLiga", is_system=True)
        kw = dict(loss=0.0, trend_d3=4.7, trend_d7=11.1, cost_basis=1_000_000)
        self.assertEqual(ap.offer_decision(o, p, **kw)[0], "hold")                       # subiendo: se aguanta
        self.assertEqual(ap.offer_decision(o, p, free_slot=True, **kw)[0], "accept")     # hace falta la plaza
        low = Offer(id="o2", money=900_000, from_manager="LaLiga", is_system=True)
        self.assertEqual(ap.offer_decision(low, p, free_slot=True, **kw)[0], "hold")     # por debajo de lo pagado, no
        # un titular nunca se vende por esto
        self.assertEqual(ap.offer_decision(o, p, free_slot=True, **{**kw, "loss": 3.0})[0], "hold")


class ReserveKeeperNotSold(unittest.TestCase):
    def test_offer_for_the_reserve_keeper_is_held(self):
        offer = Offer(id="o", money=1_200_000, from_manager="LaLiga", is_system=True)
        d, why = ap.offer_decision(offer, gk("b"), loss=0.0, reserve_keeper=True)
        self.assertEqual(d, "hold")
        self.assertIn("reserva", why)
        self.assertEqual(ap.offer_decision(offer, gk("b"), loss=0.0, reserve_keeper=False)[0], "accept")


class BidCleanup(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")
        self.p = Player(id="alonso", name="Marcos Alonso", position_id=2, team="T", team_id="t", market_value=21_800_000,
                        points=29, avg_points=4.8, status="ok")

    def world(self, my_bid, hours):
        it = MarketItem(player=self.p, price=21_800_000, expires=NOW + timedelta(hours=20), seller="LaLiga", bids=0,
                        market_id="m1", my_bid=my_bid, my_bid_id="b1" if my_bid else "")
        freeze = (datetime.now(timezone.utc) + timedelta(hours=hours - 24), datetime.now(timezone.utc) + timedelta(hours=hours))
        return SimpleNamespace(market=[it], league_id="L", clause_freeze=freeze)

    def test_cancelled_bid_stops_reserving_money(self):
        self.store.add_market_bid("alonso", "Marcos Alonso", 21_800_000, time.time() + 3600)
        self.store.db.execute("UPDATE market_bids SET created_at = ?", (time.time() - 3600,)); self.store.db.commit()
        committed, incoming = cli._committed_bids(self.store, self.world(my_bid=0, hours=100))
        self.assertEqual((committed, incoming), (0, []))
        self.assertEqual(self.store.unresolved_market_bids("buy"), [])        # quedó marcada como cancelada

    def test_fresh_bid_not_yet_visible_still_counts(self):
        self.store.add_market_bid("alonso", "Marcos Alonso", 21_800_000, time.time() + 3600)   # recién hecha en esta pasada
        committed, _ = cli._committed_bids(self.store, self.world(my_bid=0, hours=100))
        self.assertEqual(committed, 21_800_000)

    def test_emergency_bid_is_cancelled_once_it_is_not_an_emergency(self):
        class API:
            cancelled = []
            def cancel_bid(self, league, market, bid): API.cancelled.append(bid)
        self.store.record_auto_op("emergency_debt_buy", "alonso", 21_800_000)
        self.store.add_market_bid("alonso", "Marcos Alonso", 21_800_000, time.time() + 3600)
        events = cli._prune_bids(self.store, API(), self.world(my_bid=21_800_000, hours=120))
        self.assertEqual(API.cancelled, ["b1"])
        self.assertTrue(any("ya no es una emergencia" in e for e in events))

    def test_real_emergency_bid_is_kept(self):
        class API:
            def cancel_bid(self, *a): raise AssertionError("no debía cancelar")
        self.store.record_auto_op("emergency_debt_buy", "alonso", 21_800_000)
        self.assertEqual(cli._prune_bids(self.store, API(), self.world(my_bid=21_800_000, hours=10)), [])


if __name__ == "__main__":
    unittest.main()
