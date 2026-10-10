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


class BackupMove(unittest.TestCase):
    def setUp(self):
        self.soria = slot(gk("soria", 7.5, 38_000_000), locked=NOW + timedelta(days=1))

    def move(self, market=(), rivals=(), slots=None, incoming=(), budget=30_000_000, freeze=FREEZE, now=NOW):
        return ap.backup_keeper_move(slots or [self.soria], list(incoming), list(market), list(rivals), now, freeze, budget)

    def test_prefers_an_open_clause_over_the_market(self):
        galdin = slot(gk("galdin", 0.0, 540_000), clause=1_000_000, owner="pep")     # cláusula 1,87× pero solo 1M
        mv = self.move(market=[item(gk("mk", 2.0, 600_000), 600_000)], rivals=[galdin])
        self.assertEqual((mv.kind, mv.player.id, mv.cost), ("clause", "galdin", 1_000_000))   # el ratio no importa

    def test_uses_the_market_when_no_clause_is_open(self):
        locked = slot(gk("locked"), locked=NOW + timedelta(days=3), owner="pep")
        mv = self.move(market=[item(gk("mk", 2.0, 600_000), 600_000)], rivals=[locked])
        self.assertEqual((mv.kind, mv.player.id), ("bid", "mk"))

    def test_picks_the_best_keeper_within_the_cap(self):
        rivals = [slot(gk("a", 1.0, 800_000), owner="x"), slot(gk("b", 3.0, 2_500_000), owner="y"), slot(gk("c", 6.0, 20_000_000), owner="z")]
        self.assertEqual(self.move(rivals=rivals).player.id, "b")        # c pasa de 3M; b juega más que a

    def test_nothing_when_covered_or_nothing_affordable(self):
        backup = slot(gk("b"), locked=NOW + timedelta(days=14))
        self.assertIsNone(self.move(slots=[self.soria, backup], rivals=[slot(gk("a"), owner="x")]))
        self.assertIsNone(self.move(rivals=[slot(gk("a", 1.0, 800_000), owner="x")], budget=500_000))

    def test_no_clause_payments_while_clauses_are_frozen(self):
        frozen = (NOW - timedelta(hours=1), NOW + timedelta(hours=20))
        self.assertIsNone(self.move(rivals=[slot(gk("a", 1.0, 800_000), owner="x")], freeze=frozen))
        self.assertEqual(self.move(market=[item(gk("mk"), 600_000)], rivals=[slot(gk("a"), owner="x")], freeze=frozen).kind, "bid")

    def test_rotation_when_the_protected_one_is_about_to_expire(self):
        old_backup = slot(gk("old"), locked=FREEZE[0] - timedelta(hours=2))     # se abre antes de la congelación
        mv = self.move(slots=[self.soria, old_backup], rivals=[slot(gk("new", 1.0, 700_000), owner="x")])
        self.assertEqual(mv.player.id, "new")

    def test_pending_bid_counts_as_protection(self):
        self.assertIsNone(self.move(incoming=[gk("coming")], rivals=[slot(gk("a"), owner="x")]))


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
