"""Tests sin red: ofertas recibidas, con la forma REAL de `GET .../playerTeam/{id}/offer`
(confirmada en vivo el 26/09/2026 con las ofertas por Sangante e Iván Martín)."""
import unittest

from fantasy_agent.models import parse_player_offers, parse_results

REAL = [
    {"id": "132884932", "money": 6622211, "status": "pending", "createdAt": "2026-09-25T20:53:10+02:00",
     "updatedAt": "2026-09-25T20:53:10+02:00", "isFromMarket": True, "expirationDate": "2026-09-26T20:53:00+02:00"},
]


class OfferParsingTests(unittest.TestCase):
    def test_real_league_offer(self):
        [o] = parse_player_offers(REAL)
        self.assertEqual((o.id, o.money), ("132884932", 6622211))
        self.assertTrue(o.is_system)
        self.assertEqual(o.from_manager, "LaLiga")
        self.assertIsNotNone(o.expires)

    def test_rival_offer_is_not_system(self):
        [o] = parse_player_offers([{**REAL[0], "isFromMarket": False}])
        self.assertFalse(o.is_system)

    def test_non_pending_offers_are_skipped(self):
        self.assertEqual(parse_player_offers([{**REAL[0], "status": "rejected"}]), [])

    def test_missing_id_is_skipped(self):
        self.assertEqual(parse_player_offers([{"money": 1}]), [])


class ResultsTests(unittest.TestCase):
    def test_only_finished_matches(self):
        cal = [
            {"localId": 20, "visitorId": 11, "matchState": 7, "localScore": 3, "visitorScore": 1},
            {"localId": 1, "visitorId": 2, "matchState": 1},
        ]
        self.assertEqual(parse_results(cal), [("20", "11", 3, 1)])


if __name__ == "__main__":
    unittest.main()
