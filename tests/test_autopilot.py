"""Tests sin red del piloto automático: compras, ofertas, venta antes de perder la
protección y alineación."""
import unittest
from datetime import datetime, timedelta, timezone

from fantasy_agent import autopilot as ap
from types import SimpleNamespace

from fantasy_agent.models import MarketItem, Offer, Player, SquadSlot

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def player(pid, pos, avg=4.0, value=10_000_000, status="ok"):
    return Player(id=pid, name=pid, position_id=pos, team="T", team_id="t", market_value=value,
                  points=int(avg * 7), avg_points=avg, status=status)


def eleven(avg=4.0):
    """Once completo 4-3-3."""
    return ([player("gk", 1, avg)] + [player(f"d{i}", 2, avg) for i in range(4)]
            + [player(f"m{i}", 3, avg) for i in range(3)] + [player(f"f{i}", 4, avg) for i in range(3)])


def item(p, price=None, bids=0):
    return MarketItem(player=p, price=price or p.market_value, expires=NOW + timedelta(hours=8),
                      seller="LaLiga", bids=bids, market_id=f"mk-{p.id}")


def rival_slot(p, clause=None, locked_until=None, owner="rival"):
    return SquadSlot(player=p, owner_team_id=owner, owner_name=owner, clause=clause or p.market_value,
                     clause_locked_until=locked_until, player_team_id=f"pt-{p.id}")


class SquadValueTests(unittest.TestCase):
    def test_complete_eleven_worth_much_more_than_incomplete(self):
        full = eleven()
        self.assertGreater(ap.squad_value(full) - ap.squad_value(full[1:]), ap.COMPLETE_XI_BONUS)

    def test_injured_player_adds_nothing_to_points(self):
        base = eleven()
        self.assertAlmostEqual(ap.squad_value(base + [player("x", 4, 9.0, status="injured")]), ap.squad_value(base))


class AcquisitionTests(unittest.TestCase):
    def test_fills_missing_goalkeeper_first(self):
        mine = eleven()[1:]  # sin portero
        moves = ap.bid_moves([item(player("gk2", 1, 3.0, 2_000_000)), item(player("star", 3, 8.0, 5_000_000))])
        plan = ap.plan_acquisitions(mine, moves, 100_000_000)
        self.assertEqual(plan[0].player.id, "gk2")

    def test_never_exceeds_budget(self):
        moves = ap.bid_moves([item(player(f"s{i}", 3, 9.0, 30_000_000)) for i in range(5)])
        plan = ap.plan_acquisitions(eleven(), moves, 50_000_000)
        self.assertLessEqual(sum(m.cost for m in plan), 50_000_000)

    def test_ignores_players_that_do_not_improve_the_eleven(self):
        moves = ap.bid_moves([item(player("meh", 3, 1.0, 1_000_000))])
        self.assertEqual(ap.plan_acquisitions(eleven(5.0), moves, 100_000_000), [])

    def test_quality_beats_cheap_filler_when_squad_slots_are_scarce(self):
        cheap = item(player("cheap", 3, 4.6, 500_000))
        star = item(player("star", 3, 9.0, 30_000_000))
        plan = ap.plan_acquisitions(eleven(), ap.bid_moves([cheap, star]), 100_000_000, max_squad=12)
        self.assertEqual([m.player.id for m in plan], ["star"])

    def test_respects_max_squad(self):
        moves = ap.bid_moves([item(player(f"s{i}", 3, 9.0, 1_000_000)) for i in range(6)])
        plan = ap.plan_acquisitions(eleven(), moves, 100_000_000, max_squad=13)
        self.assertEqual(len(plan), 2)

    def test_skips_listings_already_bid_on(self):
        it = item(player("x", 3, 9.0))
        it.my_bid = it.price
        self.assertEqual(ap.bid_moves([it]), [])

    def test_only_laliga_listings_are_biddable(self):
        it = item(player("x", 3, 9.0))
        it.seller = "Pepe"
        self.assertEqual(ap.bid_moves([it]), [])

    def test_overbid_capped(self):
        it = item(player("x", 3, 9.0, 10_000_000), bids=3)
        self.assertLessEqual(ap.bid_amount(it, gain=10), 10_000_000 * (1 + ap.MAX_OVERBID))


class ClauseMoveTests(unittest.TestCase):
    def test_open_logical_clause_is_executable_now(self):
        [m] = ap.clause_moves([rival_slot(player("r", 4, 7.0))], NOW)
        self.assertTrue(m.executable_now)

    def test_expensive_clause_ignored(self):
        p = player("r", 4, 7.0)
        self.assertEqual(ap.clause_moves([rival_slot(p, clause=int(p.market_value * 1.5))], NOW), [])

    def test_clause_unlocking_soon_only_reserves_money(self):
        [m] = ap.clause_moves([rival_slot(player("r", 1, 6.0), locked_until=NOW + timedelta(hours=10))], NOW)
        self.assertFalse(m.executable_now)
        self.assertEqual(m.unlock_at, NOW + timedelta(hours=10))

    def test_clause_unlocking_far_away_ignored(self):
        slot = rival_slot(player("r", 1, 6.0), locked_until=NOW + timedelta(days=5))
        self.assertEqual(ap.clause_moves([slot], NOW), [])

    def test_no_clauses_during_freeze(self):
        freeze = (NOW - timedelta(hours=1), NOW + timedelta(hours=23))
        [m] = ap.clause_moves([rival_slot(player("r", 4, 7.0))], NOW, freeze=freeze)
        self.assertFalse(m.executable_now)

    def test_leader_is_penalized_not_excluded(self):
        [m] = ap.clause_moves([rival_slot(player("r", 4, 7.0), owner="lider")], NOW, avoid_team_ids=frozenset({"lider"}))
        self.assertTrue(m.penalized)


class OfferDecisionTests(unittest.TestCase):
    def offer(self, money, system=True):
        return Offer(id="o1", money=money, from_manager="LaLiga" if system else "Pepe", is_system=system)

    def test_generous_league_offer_accepted(self):
        d, _ = ap.offer_decision(self.offer(11_200_000), player("p", 3), loss=1.0)
        self.assertEqual(d, "accept")

    def test_below_value_league_offer_held(self):
        d, _ = ap.offer_decision(self.offer(9_800_000), player("p", 3), loss=1.0)
        self.assertEqual(d, "hold")

    def test_key_player_needs_much_more(self):
        d, _ = ap.offer_decision(self.offer(11_200_000), player("p", 3), loss=5.0)
        self.assertEqual(d, "hold")

    def test_rival_offer_rejected_unless_exceptional(self):
        self.assertEqual(ap.offer_decision(self.offer(11_000_000, False), player("p", 3), loss=0)[0], "reject")
        self.assertEqual(ap.offer_decision(self.offer(14_000_000, False), player("p", 3), loss=0)[0], "accept")

    def test_never_breaks_the_eleven_right_before_the_jornada(self):
        d, _ = ap.offer_decision(self.offer(20_000_000), player("p", 3), loss=1.0, breaks_xi=True, hours_to_deadline=20)
        self.assertEqual(d, "hold")

    def test_last_day_before_protection_ends_sells_at_value(self):
        self.assertEqual(ap.offer_decision(self.offer(9_900_000), player("p", 3), loss=1.0, exposed_in=10)[0], "hold")
        self.assertEqual(ap.offer_decision(self.offer(10_050_000), player("p", 3), loss=1.0, exposed_in=10)[0], "accept")

    def test_never_sells_below_what_the_clause_would_pay(self):
        # Caso Soria: pagado 46,6M, vale 38,3M, cláusula 46,6M. Si se lo llevan, cobro 46,6M.
        p = player("p", 1)
        p.market_value = 38_300_000
        d, why = ap.offer_decision(self.offer(41_000_000), p, loss=0, exposed_in=10, clause=46_650_000, cut_loss=True)
        self.assertEqual(d, "hold")
        self.assertIn("clausulan", why)
        self.assertEqual(ap.offer_decision(self.offer(47_000_000), p, loss=0, exposed_in=10, clause=46_650_000)[0], "accept")

    def test_three_days_before_protection_ends_needs_a_good_offer(self):
        p = player("p", 3)
        self.assertEqual(ap.offer_decision(self.offer(10_100_000), p, loss=1.0, exposed_in=70)[0], "hold")
        self.assertEqual(ap.offer_decision(self.offer(10_400_000), p, loss=1.0, exposed_in=70)[0], "accept")

    def test_bids_wait_for_the_last_minute(self):
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        it = lambda m: SimpleNamespace(expires=now + timedelta(minutes=m))  # noqa: E731
        self.assertEqual(ap.bid_timing(it(8 * 60), now), "wait")
        self.assertEqual(ap.bid_timing(it(40), now), "wait")
        self.assertEqual(ap.bid_timing(it(20), now), "late")   # este job espera y puja a falta de 2,5 min
        self.assertEqual(ap.bid_timing(it(2), now), "now")
        self.assertEqual(ap.bid_timing(SimpleNamespace(expires=None), now), "now")

    def test_rising_player_is_kept_even_near_its_clause(self):
        p = player("p", 3)
        d, why = ap.offer_decision(self.offer(10_400_000), p, loss=1.0, exposed_in=30, trend_d3=4, trend_d7=12, clause=10_000_000)
        self.assertEqual(d, "hold")
        self.assertIn("subiendo", why)

    def test_leader_players_at_fair_clause_get_priority(self):
        now = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        mk = lambda owner, clause: SquadSlot(player=player("x" + owner + str(clause), 3), owner_team_id=owner, owner_name=owner,  # noqa: E731
                                              clause=clause, clause_locked_until=None, player_team_id="pt")
        moves = ap.clause_moves([mk("L", 10_000_000), mk("L", 11_500_000), mk("R", 10_000_000)], now,
                                avoid_team_ids=frozenset({"L"}), leader_team_id="L")
        flags = [(m.slot.owner_team_id, m.slot.clause, m.bonus, m.penalized) for m in moves]
        self.assertIn(("L", 10_000_000, True, False), flags)    # a su valor: no le regalo nada y pierde puntos
        self.assertIn(("L", 11_500_000, False, True), flags)    # con prima: le regalaría dinero
        self.assertIn(("R", 10_000_000, False, False), flags)

    def test_backup_keeper_only_with_a_single_keeper(self):
        def gk(pid, price, avg, pts=10):
            pl = player(pid, 1); pl.avg_points, pl.points = avg, pts
            return SimpleNamespace(player=pl, price=price, seller="LaLiga", market_id="m" + pid, my_bid=0)
        market = [gk("a", 900_000, 3.0), gk("b", 600_000, 4.0), gk("c", 3_000_000, 6.0), gk("d", 500_000, 5.0, pts=0)]
        self.assertEqual(ap.backup_keeper([player("mine", 1)], market, 10_000_000).player.id, "b")
        self.assertIsNone(ap.backup_keeper([player("mine", 1), player("mine2", 1)], market, 10_000_000))
        self.assertEqual(ap.backup_keeper([player("mine", 1)], market, 700_000).player.id, "b")
        self.assertIsNone(ap.backup_keeper([player("mine", 1)], market, 400_000))

    def test_at_risk_threshold_decreases_as_protection_ends(self):
        self.assertGreater(ap.at_risk_min(72, key=False), ap.at_risk_min(48, key=False))
        self.assertGreater(ap.at_risk_min(48, key=False), ap.at_risk_min(10, key=False))
        self.assertGreater(ap.at_risk_min(10, key=True), ap.at_risk_min(10, key=False))


class ExposureTests(unittest.TestCase):
    def slot(self, clause_ratio, locked_until=None):
        p = player("mine", 3)
        return SquadSlot(player=p, owner_team_id="me", owner_name="yo", clause=int(p.market_value * clause_ratio),
                         clause_locked_until=locked_until, player_team_id="pt")

    def test_high_clause_is_not_a_target(self):
        self.assertIsNone(ap.hours_until_exposed(self.slot(2.0), NOW))

    def test_open_logical_clause_is_exposed_now(self):
        self.assertEqual(ap.hours_until_exposed(self.slot(1.0), NOW), 0.0)

    def test_hours_until_protection_ends(self):
        self.assertAlmostEqual(ap.hours_until_exposed(self.slot(1.0, NOW + timedelta(hours=30)), NOW), 30.0)


class SaleLossTests(unittest.TestCase):
    def test_losing_a_starter_costs_his_points(self):
        mine = eleven(4.0)
        self.assertGreater(ap.sale_loss(mine, "m0"), 3.0)

    def test_bench_player_costs_little(self):
        mine = eleven(4.0) + [player("bench", 3, 1.0)]
        self.assertLess(ap.sale_loss(mine, "bench"), 0.5)

    def test_breaks_eleven(self):
        self.assertTrue(ap.breaks_eleven(eleven(), "gk"))
        self.assertFalse(ap.breaks_eleven(eleven() + [player("gk2", 1)], "gk"))


class BidAmountTests(unittest.TestCase):
    def test_no_competition_bids_a_small_premium(self):
        it = item(player("x", 3, 9.0, 10_000_000))
        self.assertEqual(ap.bid_amount(it, gain=4.0), round(10_000_000 * 1.06))

    def test_competition_matches_what_rivals_pay(self):
        it = item(player("x", 3, 9.0, 10_000_000), bids=1)
        rivals = ap.RivalPremium(median=1.09, p75=1.23)
        self.assertEqual(ap.bid_amount(it, gain=4.0, rivals=rivals), round(10_000_000 * 1.11))

    def test_never_above_cap(self):
        it = item(player("x", 3, 9.0, 10_000_000), bids=3)
        rivals = ap.RivalPremium(median=1.3, p75=1.6)
        self.assertEqual(ap.bid_amount(it, gain=4.0, rivals=rivals), round(10_000_000 * (1 + ap.MAX_OVERBID)))

    def test_rival_premium_ignored_without_competition(self):
        it = item(player("x", 3, 9.0, 10_000_000))
        rivals = ap.RivalPremium(median=1.15, p75=1.2)
        self.assertEqual(ap.bid_amount(it, gain=0.8, rivals=rivals), round(10_000_000 * 1.03))


class FallingTests(unittest.TestCase):
    def test_falling_value_is_skipped(self):
        self.assertTrue(ap.is_falling(-4, 0))
        self.assertTrue(ap.is_falling(0, -7))
        self.assertFalse(ap.is_falling(-1, -2))
        self.assertFalse(ap.is_falling(2, 5))


class CostBasisTests(unittest.TestCase):
    def offer(self, money):
        return Offer(id="o", money=money, from_manager="LaLiga", is_system=True)

    def test_does_not_sell_below_what_was_paid(self):
        p = player("p", 3, value=10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(10_600_000), p, loss=1.0, cost_basis=11_500_000)[0], "hold")
        self.assertEqual(ap.offer_decision(self.offer(11_600_000), p, loss=1.0, cost_basis=11_500_000)[0], "accept")

    def test_cut_loss_ignores_the_cost_but_clause_risk_does_not(self):
        p = player("p", 3, value=10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(9_900_000), p, loss=1.0, cut_loss=True, cost_basis=14_000_000)[0], "accept")
        self.assertEqual(ap.offer_decision(self.offer(9_900_000), p, loss=1.0, exposed_in=10, cost_basis=14_000_000)[0], "hold")
        self.assertEqual(ap.offer_decision(self.offer(14_100_000), p, loss=1.0, exposed_in=10, cost_basis=14_000_000)[0], "accept")


class MoreOfferRulesTests(unittest.TestCase):
    offer = Offer(id="o", money=10_600_000, from_manager="LaLiga", is_system=True)

    def test_starter_not_sold_right_before_the_jornada(self):
        self.assertEqual(ap.offer_decision(self.offer, player("p", 3), loss=1.5, hours_to_deadline=30)[0], "hold")
        self.assertEqual(ap.offer_decision(self.offer, player("p", 3), loss=1.5, hours_to_deadline=100)[0], "accept")

    def test_bench_player_sold_at_value_when_squad_is_full(self):
        cheap = Offer(id="o", money=9_800_000, from_manager="LaLiga", is_system=True)
        self.assertEqual(ap.offer_decision(cheap, player("p", 3), loss=0.2, squad_full=True)[0], "accept")
        self.assertEqual(ap.offer_decision(cheap, player("p", 3), loss=0.2, squad_full=False)[0], "hold")


class FixtureFactorTests(unittest.TestCase):
    def test_home_against_the_worst_team_is_best(self):
        self.assertGreater(ap.fixture_factor(True, 20), ap.fixture_factor(False, 1))

    def test_unknown_fixture_is_neutral(self):
        self.assertEqual(ap.fixture_factor(None, None), 1.0)


class LineupPayloadTests(unittest.TestCase):
    ids = {1: ["g"], 2: ["d1", "d2", "d3", "d4"], 3: ["m1", "m2", "m3"], 4: ["f1", "f2", "f3"]}

    def test_flat(self):
        body = ap.lineup_payload((4, 3, 3), self.ids, "flat")
        self.assertEqual(body["goalkeeper"], "g")
        self.assertEqual(body["tacticalFormation"], [4, 3, 3])

    def test_nested_mirrors_get_shape(self):
        body = ap.lineup_payload((4, 3, 3), self.ids, "nested")
        self.assertEqual(body["formation"]["goalkeeper"], ["g"])

    def test_ids_read_back_from_get(self):
        got = {"formation": {"goalkeeper": [{"playerTeamId": "g"}], "defender": [{"playerTeamId": "d1"}],
                             "midfield": [], "striker": [], "bench": {}, "tacticalFormation": [4, 3, 3]}}
        self.assertEqual(ap.lineup_ids(got), {"g", "d1"})


if __name__ == "__main__":
    unittest.main()


class InvestmentTests(unittest.TestCase):
    from fantasy_agent.analysis import Trend

    def test_buys_only_sustained_risers(self):
        T = self.Trend
        market = [item(player("up", 3, 4.0, 5_000_000)), item(player("flat", 3, 4.0, 5_000_000)),
                  item(player("down", 3, 4.0, 5_000_000))]
        trends = {"up": T(2, 5, 8), "flat": T(0, 1, 1), "down": T(-3, -5, -9)}
        self.assertEqual([m.player.id for m in ap.invest_moves(market, trends)], ["up"])

    def test_skips_expensive_listing_and_injured(self):
        T = self.Trend
        pricey = item(player("p", 3, 4.0, 5_000_000), price=6_000_000)
        hurt = item(player("h", 3, 4.0, 5_000_000, status="injured"))
        trends = {"p": T(2, 5, 8), "h": T(2, 5, 8)}
        self.assertEqual(ap.invest_moves([pricey, hurt], trends), [])

    def test_strongest_momentum_first_and_budget_respected(self):
        T = self.Trend
        market = [item(player("a", 3, 4.0, 10_000_000)), item(player("b", 3, 4.0, 10_000_000))]
        trends = {"a": T(2, 5, 7), "b": T(3, 9, 15)}
        moves = ap.invest_moves(market, trends)
        self.assertEqual(moves[0].player.id, "b")
        self.assertEqual([m.player.id for m in ap.plan_investments(moves, budget=28_000_000, slots=5)], ["b", "a"])
        self.assertEqual(ap.plan_investments(moves, budget=12_000_000, slots=5), [])  # sobrepasa el tope por jugador
        self.assertEqual([m.player.id for m in ap.plan_investments(moves, budget=28_000_000, slots=1)], ["b"])

    def test_respects_free_squad_slots(self):
        T = self.Trend
        market = [item(player(f"x{i}", 3, 4.0, 1_000_000)) for i in range(4)]
        trends = {f"x{i}": T(2, 5, 8) for i in range(4)}
        self.assertEqual(len(ap.plan_investments(ap.invest_moves(market, trends), budget=100_000_000, slots=2)), 2)


class ClauseInvestmentTests(unittest.TestCase):
    from fantasy_agent.analysis import Trend

    def test_rising_player_with_fair_clause_is_an_investment(self):
        T = self.Trend
        p = player("riser", 3, 4.0, 10_000_000)
        out = ap.clause_invest_moves([rival_slot(p)], {"riser": T(2, 6, 10)}, NOW)
        self.assertEqual([(m.kind, m.player.id) for m in out], [("invest_clause", "riser")])

    def test_expensive_clause_or_flat_player_is_ignored(self):
        T = self.Trend
        p = player("riser", 3, 4.0, 10_000_000)
        self.assertEqual(ap.clause_invest_moves([rival_slot(p, clause=11_500_000)], {"riser": T(2, 6, 10)}, NOW), [])
        self.assertEqual(ap.clause_invest_moves([rival_slot(p)], {"riser": T(0, 1, 2)}, NOW), [])

    def test_clause_unlocking_soon_is_reserved_not_executed(self):
        T = self.Trend
        p = player("riser", 3, 4.0, 10_000_000)
        out = ap.clause_invest_moves([rival_slot(p, locked_until=NOW + timedelta(hours=6))], {"riser": T(2, 6, 10)}, NOW)
        self.assertFalse(out[0].executable_now)

    def test_plans_clause_and_market_investments_together(self):
        T = self.Trend
        a = player("a", 3, 4.0, 10_000_000)
        b = player("b", 3, 4.0, 5_000_000)
        trends = {"a": T(2, 6, 10), "b": T(3, 9, 20)}
        moves = ap.clause_invest_moves([rival_slot(a)], trends, NOW) + ap.invest_moves([item(b)], trends)
        chosen = ap.plan_investments(moves, budget=60_000_000, slots=5)
        self.assertEqual({m.kind for m in chosen}, {"invest_clause", "invest"})
        self.assertEqual(chosen[0].player.id, "b")  # más momentum primero


class DriftTests(unittest.TestCase):
    def test_expected_drift_levels(self):
        self.assertEqual(ap.expected_drift(5, 8), 0.15)             # sin datos de forma: valor neutro
        self.assertEqual(ap.expected_drift(5, 8, form=8), 0.25)     # subida fuerte + buena forma
        self.assertEqual(ap.expected_drift(5, 8, form=0.5), 0.08)   # subida sin puntos que la respalden
        self.assertEqual(ap.expected_drift(2.5, 1, form=7), 0.08)   # entrada anticipada: forma buena, subida suave
        self.assertEqual(ap.expected_drift(2.5, 4, form=1), 0.0)    # subida suave sin forma: nada
        self.assertEqual(ap.expected_drift(0, 1, form=9), 0.0)      # forma buena con precio plano: nada
        self.assertEqual(ap.expected_drift(-1, -3, form=9), ap.DRIFT_DECLINING)  # bajando un poco: cuesta
        self.assertLess(ap.DRIFT_DECLINING, 0)

    def test_rising_candidate_beats_an_equal_flat_one(self):
        mine = eleven()[:-1]            # falta un delantero
        flat, riser = player("flat", 4, 5.0, 10_000_000), player("riser", 4, 5.0, 10_000_000)
        moves = ap.bid_moves([item(flat), item(riser)])
        for m in moves:
            m.drift = 0.17 if m.player.id == "riser" else 0.0
        plan = ap.plan_acquisitions(mine, moves, budget=30_000_000, max_squad=len(mine) + 1)
        self.assertEqual([m.player.id for m in plan], ["riser"])


class AnticipationAndLiquidityTests(unittest.TestCase):
    from fantasy_agent.analysis import Trend

    def test_good_form_with_a_mild_rise_is_an_early_entry(self):
        T = self.Trend
        p = player("early", 3, 6.0, 8_000_000)
        trends = {"early": T(1, 2.5, 3)}
        self.assertEqual(ap.invest_moves([item(p)], trends), [])  # sin datos de forma no entra
        self.assertEqual([m.player.id for m in ap.invest_moves([item(p)], trends, form={"early": 7.5})], ["early"])
        self.assertEqual(ap.invest_moves([item(p)], trends, form={"early": 1.0}), [])

    def test_strong_rise_with_good_form_ranks_first(self):
        T = self.Trend
        a, b = player("a", 3, 5.0, 8_000_000), player("b", 3, 5.0, 8_000_000)
        trends = {"a": T(2, 5, 8), "b": T(2, 5, 8)}
        moves = ap.invest_moves([item(a), item(b)], trends, form={"a": 1.0, "b": 9.0})
        self.assertEqual(moves[0].player.id, "b")

    def test_liquidity_sells_a_flat_bench_player_below_cost(self):
        o = Offer(id="o", money=9_800_000, from_manager="LaLiga", is_system=True)
        p = player("bench", 3, 1.0, 10_000_000)
        self.assertEqual(ap.offer_decision(o, p, loss=0.2, cost_basis=11_000_000)[0], "hold")
        self.assertEqual(ap.offer_decision(o, p, loss=0.2, cost_basis=11_000_000, liquidity=True)[0], "accept")

    def test_liquidity_never_sells_a_starter_or_a_riser(self):
        o = Offer(id="o", money=9_800_000, from_manager="LaLiga", is_system=True)
        p = player("x", 3, 5.0, 10_000_000)
        self.assertNotEqual(ap.offer_decision(o, p, loss=2.0, liquidity=True)[0], "accept")
        self.assertEqual(ap.offer_decision(o, p, loss=0.2, trend_d7=12, liquidity=True)[0], "hold")


class RelistTests(unittest.TestCase):
    def test_relist_when_value_rose_10_percent(self):
        self.assertTrue(ap.needs_relist(ask=11_000_000, value_now=12_500_000, mult=1.1))
        self.assertFalse(ap.needs_relist(ask=11_000_000, value_now=10_500_000, mult=1.1))

    def test_relist_when_the_ask_is_far_above_a_collapsed_value(self):
        self.assertTrue(ap.needs_relist(ask=11_000_000, value_now=6_000_000, mult=1.1))

    def test_experiment_players_use_their_multiplier_until_it_ends(self):
        from datetime import datetime, timezone
        before = datetime(2026, 10, 5, tzinfo=timezone.utc)
        after = datetime(2026, 10, 20, tzinfo=timezone.utc)
        self.assertEqual(ap.ask_multiplier("3239", before), 2.0)
        self.assertEqual(ap.ask_multiplier("3239", after), ap.LISTING_MARKUP)
        self.assertEqual(ap.ask_multiplier("someone", before), ap.LISTING_MARKUP)
        self.assertTrue(ap.needs_relist(ask=1_110_000, value_now=1_070_000, mult=2.0))  # el anuncio aún es el normal


class HoldRisersTests(unittest.TestCase):
    def offer(self, ratio):
        return Offer(id="o", money=int(10_000_000 * ratio), from_manager="LaLiga", is_system=True)

    def test_a_riser_is_not_sold_while_it_keeps_rising(self):
        p = player("r", 4, 6.0, 10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(1.12), p, loss=0.2, trend_d3=4, trend_d7=12)[0], "hold")

    def test_it_is_sold_once_the_rise_stalls(self):
        p = player("r", 4, 6.0, 10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(1.06), p, loss=0.2, trend_d3=0.2, trend_d7=12)[0], "accept")

    def test_a_flat_player_follows_the_normal_threshold(self):
        p = player("f", 4, 6.0, 10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(1.06), p, loss=0.2, trend_d3=0.3, trend_d7=1)[0], "accept")
        self.assertEqual(ap.offer_decision(self.offer(1.02), p, loss=0.2, trend_d3=0.3, trend_d7=1)[0], "hold")


class NetBenefitTests(unittest.TestCase):
    """Caso real del 5/10: Johnny (5,04M de valor) se clausuló por 6M aportando ~0,6 pts/jornada."""

    def plan(self, avg, clause=6_000_000, drift=0.15):
        p = player("cand", 3, avg, 5_040_000)
        [m] = ap.clause_moves([rival_slot(p, clause=clause)], NOW)
        m.drift = drift
        return ap.plan_acquisitions(eleven(4.0), [m], budget=50_000_000, max_squad=16)

    def test_a_19_percent_premium_for_a_marginal_upgrade_is_rejected(self):
        self.assertEqual(self.plan(avg=4.0), [])   # +0,6 pts/jornada, como Johnny

    def test_the_same_premium_is_fine_for_a_big_upgrade(self):
        self.assertEqual(len(self.plan(avg=9.0)), 1)

    def test_a_clause_at_value_is_fine_for_a_small_upgrade(self):
        self.assertEqual(len(self.plan(avg=4.6, clause=5_040_000, drift=0.0)), 1)

    def test_investment_needs_to_beat_the_premium(self):
        T = InvestmentTests.Trend
        p = player("x", 3, 4.0, 5_000_000)
        early = {"x": T(1, 2.5, 3)}                          # entrada anticipada: ~+8% esperado
        pricey = [rival_slot(p, clause=5_150_000)]          # +3% de prima: ya no queda margen tras el spread
        self.assertEqual(ap.clause_invest_moves(pricey, early, NOW, form={"x": 8.0}), [])
        fair = [rival_slot(p, clause=5_000_000)]
        self.assertEqual(len(ap.clause_invest_moves(fair, early, NOW, form={"x": 8.0})), 1)


class InjuredSaleTests(unittest.TestCase):
    """Caso real del 5/10: Koski, lesionado y subiendo, no se vendía por la regla de 'dejar correr'."""

    def offer(self, ratio):
        return Offer(id="o", money=int(10_000_000 * ratio), from_manager="LaLiga", is_system=True)

    def test_healthy_riser_is_held(self):
        p = player("k", 2, 7.0, 10_000_000)
        self.assertEqual(ap.offer_decision(self.offer(1.01), p, loss=0.0, trend_d3=7, trend_d7=25)[0], "hold")

    def test_injured_riser_is_sold_at_value(self):
        p = player("k", 2, 7.0, 10_000_000, status="injured")
        self.assertEqual(ap.offer_decision(self.offer(1.01), p, loss=0.0, trend_d3=7, trend_d7=25, injured=True)[0], "accept")

    def test_injured_still_respects_the_cost(self):
        p = player("k", 2, 7.0, 10_000_000, status="injured")
        self.assertEqual(ap.offer_decision(self.offer(1.01), p, loss=0.0, injured=True, cost_basis=11_000_000)[0], "hold")
