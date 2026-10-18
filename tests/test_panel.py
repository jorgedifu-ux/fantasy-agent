"""Panel y gráficas: nombres cortos, jornada legible y configuraciones de gráfica bien formadas."""
import unittest
from datetime import datetime, timezone

from fantasy_agent import charts, panel


class Names(unittest.TestCase):
    def test_short_names(self):
        self.assertEqual([panel.short_name(n) for n in ("JosinhoPermanbucano", "ALEIX VIDEL", "Pep Callaba", "The Iberian One")],
                         ["Josinho", "Aleix", "Pep", "Iberian"])
        self.assertEqual(panel.short_name("The Iberian One", me=True), "Tú")


class Jornada(unittest.TestCase):
    def test_lines_show_points_pending_matches_and_sold_players(self):
        d = {"rows": [{"pos": "DEF", "name": "Hancko", "pts": 10, "when": None},
                      {"pos": "POR", "name": "Soria", "pts": None, "when": datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)}],
             "sold": 6}
        lines = panel.jornada_lines(d)
        self.assertIn("DEF Hancko · <b>10</b>", lines[0])
        self.assertIn("POR Soria · – (lun", lines[1])
        self.assertIn("+ 6 de jugadores vendidos", lines[2])


class Charts(unittest.TestCase):
    def test_wealth_chart_carries_the_data_the_gap_and_labels_the_last_point(self):
        cfg = charts.wealth_config(["2026-10-17", "2026-10-18"], [295.0, 298.8], [517.9, 521.8], "Josinho", "Tú")
        self.assertIn("521.8", cfg)
        self.assertIn("diferencia hoy 223M", cfg)
        self.assertIn("datalabels", cfg)

    def test_points_chart_marks_the_live_week(self):
        cfg = charts.points_config([8, 9], [57, 16], [62, 38], "Josinho", "Tú", live_week=9)
        self.assertIn("J9 (en juego)", cfg)
        self.assertIn("tú -", cfg)


if __name__ == "__main__":
    unittest.main()
