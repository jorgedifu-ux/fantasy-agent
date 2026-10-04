"""Tests sin red: detección de parones del calendario."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fantasy_agent import service

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class FakeAPI:
    def __init__(self, weeks, current):
        self.weeks, self.current = weeks, current

    def current_week(self):
        return {"weekNumber": self.current}

    def calendar(self, week):
        d = self.weeks.get(week)
        if not d:
            return []
        first, last = d
        return [{"localId": 1, "visitorId": 2, "matchDate": first.isoformat()},
                {"localId": 3, "visitorId": 4, "matchDate": last.isoformat()}]


def span(start_day, days=3):
    s = NOW + timedelta(days=start_day)
    return (s, s + timedelta(days=days))


class OutlookTests(unittest.TestCase):
    def run_outlook(self, weeks, current):
        with patch("fantasy_agent.service.datetime") as dt:
            dt.now.return_value = NOW
            dt.side_effect = lambda *a, **k: datetime(*a, **k)
            return service.calendar_outlook(FakeAPI(weeks, current), weeks_ahead=6)

    def test_break_in_progress(self):
        out = self.run_outlook({7: span(-18), 8: span(5), 9: span(12)}, current=8)
        self.assertTrue(out.in_break)
        self.assertEqual(out.next_first, span(5)[0])

    def test_normal_week_is_not_a_break(self):
        out = self.run_outlook({7: span(-2), 8: span(4), 9: span(11)}, current=8)
        self.assertFalse(out.in_break)

    def test_finds_the_next_break(self):
        out = self.run_outlook({7: span(-2), 8: span(4), 9: span(11), 10: span(32)}, current=8)
        self.assertIsNotNone(out.next_break)
        self.assertGreaterEqual((out.next_break[1] - out.next_break[0]).days, service.BREAK_GAP_DAYS)


if __name__ == "__main__":
    unittest.main()
