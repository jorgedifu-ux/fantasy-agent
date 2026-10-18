"""LaLiga resolvió el mercado con 2 h de retraso (18/10): las pujas no se dan por perdidas hasta que la liga lo diga o pase una gracia larga."""
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fantasy_agent import cli
from fantasy_agent.storage import Store


class FakeAPI:
    def __init__(self, items=()):
        self.items = list(items)

    def activity(self, league_id, page):
        return self.items if page == 0 else []

    def players(self):
        return [{"id": "7", "nickname": "Rockson", "positionId": 2, "teamId": 12, "marketValue": 670000, "points": 1, "averagePoints": 0.2, "playerStatus": "ok"}]


def world(my_ids=()):
    slots = [SimpleNamespace(player=SimpleNamespace(id=i)) for i in my_ids]
    return SimpleNamespace(my_slots=slots, league_id="L", my_team_id="me", team_names={"12": "Málaga CF"}, market=[],
                           standing=[SimpleNamespace(team_id="me", manager_id=1, manager_name="The Iberian One"),
                                     SimpleNamespace(team_id="r", manager_id=2, manager_name="JosinhoPermanbucano")])


class LateMarket(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")
        self.store.add_market_bid("7", "Rockson", 710_000, time.time() - 1800)       # cerró hace 30 min

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def test_a_bid_closed_30_minutes_ago_is_not_lost_yet(self):
        self.assertEqual(cli._check_bid_resolutions(self.store, world(), FakeAPI()), [])
        self.assertEqual(len(self.store.unresolved_market_bids("buy")), 1)

    def test_it_still_counts_as_committed_money_and_incoming_player(self):
        committed, incoming = cli._committed_bids(self.store, world(), FakeAPI())
        self.assertEqual(committed, 710_000)
        self.assertEqual([p.name for p in incoming], ["Rockson"])
        self.assertEqual(incoming[0].position_id, 2)

    def test_when_the_league_says_another_manager_won_it_is_lost_with_the_winner_named(self):
        items = [{"activityTypeId": 31, "playerMasterId": "7", "user1Id": "2", "amount": 800_000, "createdAt": datetime.now(timezone.utc).isoformat()}]
        msgs = cli._check_bid_resolutions(self.store, world(), FakeAPI(items))
        self.assertIn("JosinhoPermanbucano", msgs[0])
        self.assertEqual(self.store.unresolved_market_bids("buy"), [])

    def test_when_the_league_says_we_won_it_is_won(self):
        items = [{"activityTypeId": 31, "playerMasterId": "7", "user1Id": "1", "amount": 710_000, "createdAt": datetime.now(timezone.utc).isoformat()}]
        self.assertIn("Puja ganada", cli._check_bid_resolutions(self.store, world(), FakeAPI(items))[0])

    def test_after_the_long_grace_without_news_it_is_lost(self):
        self.store.db.execute("UPDATE market_bids SET expires_at = ?", (time.time() - 4 * 3600,))
        self.store.db.commit()
        self.assertIn("Puja perdida", cli._check_bid_resolutions(self.store, world(), FakeAPI())[0])


if __name__ == "__main__":
    unittest.main()
