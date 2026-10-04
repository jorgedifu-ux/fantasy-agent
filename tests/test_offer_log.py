import tempfile
import unittest
from pathlib import Path

from fantasy_agent.storage import Store


class OfferLogTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.db")

    def test_ratios_are_sorted_and_deduplicated(self):
        self.store.log_offer("a", "p1", "J1", 10_000_000, 10_500_000, True)
        self.store.log_offer("a", "p1", "J1", 10_000_000, 10_500_000, True)  # misma oferta vista otra vez
        self.store.log_offer("b", "p2", "J2", 10_000_000, 9_000_000, True)
        self.assertEqual([round(r, 2) for r in self.store.offer_ratios()], [0.9, 1.05])

    def test_rival_offers_are_excluded_by_default(self):
        self.store.log_offer("a", "p1", "J1", 10_000_000, 15_000_000, False)
        self.assertEqual(self.store.offer_ratios(), [])
        self.assertEqual(len(self.store.offer_ratios(system_only=False)), 1)


if __name__ == "__main__":
    unittest.main()
