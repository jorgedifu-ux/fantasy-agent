"""Test sin red: detectar quién te ha clausulado recientemente, usando la forma REAL de
`/activity` confirmada en vivo (22/09/2026) — lista plana de dicts con activityTypeId,
user1Id/user2Id (manager_id, no team_id), playerMasterId, amount, createdAt."""
import unittest
from datetime import datetime, timedelta, timezone

from fantasy_agent.service import recent_clauser_manager_id


class FakeAPI:
    def __init__(self, activity):
        self._activity = activity

    def activity(self, league_id, index=0):
        return self._activity


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class RecentClauserTests(unittest.TestCase):
    def test_recent_clause_against_me_is_detected(self):
        now = datetime.now(timezone.utc)
        activity = [
            {"activityTypeId": 1, "id": "a1", "user1Id": "666", "user2Id": "me-mgr",
             "playerMasterId": "P1", "amount": 8_000_000, "createdAt": iso(now - timedelta(hours=2))},
        ]
        api = FakeAPI(activity)
        self.assertEqual(recent_clauser_manager_id(api, "L1", "me-mgr"), "666")

    def test_ignores_clauses_against_someone_else(self):
        now = datetime.now(timezone.utc)
        activity = [
            {"activityTypeId": 1, "id": "a1", "user1Id": "666", "user2Id": "other-mgr",
             "playerMasterId": "P1", "amount": 8_000_000, "createdAt": iso(now - timedelta(hours=2))},
        ]
        api = FakeAPI(activity)
        self.assertIsNone(recent_clauser_manager_id(api, "L1", "me-mgr"))

    def test_ignores_non_clause_activity(self):
        now = datetime.now(timezone.utc)
        activity = [
            {"activityTypeId": 33, "id": "a1", "user1Id": "666", "user2Id": "me-mgr",
             "playerMasterId": "P1", "amount": 8_000_000, "createdAt": iso(now - timedelta(hours=2))},
        ]
        api = FakeAPI(activity)
        self.assertIsNone(recent_clauser_manager_id(api, "L1", "me-mgr"))

    def test_ignores_old_clauses_outside_window(self):
        now = datetime.now(timezone.utc)
        activity = [
            {"activityTypeId": 1, "id": "a1", "user1Id": "666", "user2Id": "me-mgr",
             "playerMasterId": "P1", "amount": 8_000_000, "createdAt": iso(now - timedelta(hours=100))},
        ]
        api = FakeAPI(activity)
        self.assertIsNone(recent_clauser_manager_id(api, "L1", "me-mgr", within_hours=72))


if __name__ == "__main__":
    unittest.main()
