"""Aprender de los rivales: emparejar compras con salidas y medir la tendencia previa."""
import unittest
from datetime import date, datetime, timedelta, timezone

from fantasy_agent import rivals

D0 = datetime(2026, 9, 1, 21, tzinfo=timezone.utc)


def hist(start, pct_day, days=30):
    return [(D0 - timedelta(days=10) + timedelta(days=i), int(start * (1 + pct_day) ** i)) for i in range(days)]


ACT = [
    {"activityTypeId": 31, "user1Id": 1, "playerMasterId": 10, "amount": 10_500_000, "createdAt": D0.isoformat()},
    {"activityTypeId": 1, "user1Id": 2, "user2Id": 1, "playerMasterId": 10, "amount": 14_000_000,
     "createdAt": (D0 + timedelta(days=15)).isoformat()},
    {"activityTypeId": 31, "user1Id": 2, "playerMasterId": 20, "amount": 5_000_000, "createdAt": D0.isoformat()},
    {"activityTypeId": 33, "user1Id": 2, "playerMasterId": 20, "amount": 4_000_000,
     "createdAt": (D0 + timedelta(days=5)).isoformat()},
]


class RivalsTests(unittest.TestCase):
    def test_trades_pair_buy_with_exit(self):
        ts = rivals.trades(ACT, {"1": "Líder", "2": "Otro"})
        by = {t.manager: t for t in ts}
        self.assertEqual((by["Líder"].how, by["Líder"].gain, by["Líder"].days), ("clausulado", 3_500_000, 15))
        self.assertEqual((by["Otro"].how, by["Otro"].gain), ("venta", -1_000_000))

    def test_buys_measure_previous_trend_and_after(self):
        h = {"10": hist(7_000_000, 0.02), "20": hist(6_000_000, -0.01)}
        bs = {b.player_id: b for b in rivals.buys(ACT, h, {"1": "L", "2": "O"}, date(2026, 10, 8)) if b.kind == "puja"}
        self.assertGreater(bs["10"].d7, 0.10)
        self.assertGreater(bs["10"].after14, 0.25)
        self.assertLess(bs["20"].d7, 0)
        table = {name: n for name, n, *_ in rivals.bucket_table(list(bs.values()))}
        self.assertEqual(table.get("<0%"), 1)


if __name__ == "__main__":
    unittest.main()
