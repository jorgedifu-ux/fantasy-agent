"""Tests sin red: distinguir ofertas del sistema vs. de un rival de la liga."""
import unittest

from fantasy_agent.models import _parse_offers


class OfferParsingTests(unittest.TestCase):
    def test_offer_without_manager_is_system(self):
        item = {"offers": [{"id": "1", "offerMoney": 1_000_000}]}
        offers = _parse_offers(item)
        self.assertTrue(offers[0].is_system)

    def test_offer_with_laliga_as_manager_is_system(self):
        item = {"offers": [{"id": "1", "offerMoney": 1_000_000, "managerName": "LaLiga"}]}
        self.assertTrue(_parse_offers(item)[0].is_system)

    def test_offer_with_real_manager_is_not_system(self):
        item = {"offers": [{"id": "1", "offerMoney": 1_000_000, "managerName": "Pepe"}]}
        offers = _parse_offers(item)
        self.assertFalse(offers[0].is_system)
        self.assertEqual(offers[0].from_manager, "Pepe")

    def test_missing_id_is_skipped(self):
        item = {"offers": [{"offerMoney": 1_000_000}]}
        self.assertEqual(_parse_offers(item), [])


if __name__ == "__main__":
    unittest.main()
