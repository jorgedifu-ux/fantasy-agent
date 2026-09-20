"""Tests sin red: horas de silencio del parte de situación."""
import unittest
from datetime import datetime

from fantasy_agent.digest import in_quiet_hours


class QuietHoursTests(unittest.TestCase):
    def test_midnight_is_quiet(self):
        self.assertTrue(in_quiet_hours(datetime(2026, 1, 1, 0, 30)))

    def test_early_morning_is_quiet(self):
        self.assertTrue(in_quiet_hours(datetime(2026, 1, 1, 6, 59)))

    def test_seven_am_is_not_quiet(self):
        self.assertFalse(in_quiet_hours(datetime(2026, 1, 1, 7, 0)))

    def test_midday_is_not_quiet(self):
        self.assertFalse(in_quiet_hours(datetime(2026, 1, 1, 13, 0)))

    def test_eleven_pm_is_quiet(self):
        self.assertTrue(in_quiet_hours(datetime(2026, 1, 1, 23, 0)))

    def test_ten_pm_is_not_quiet(self):
        self.assertFalse(in_quiet_hours(datetime(2026, 1, 1, 22, 59)))


if __name__ == "__main__":
    unittest.main()
