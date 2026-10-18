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
    D = {"rows": [{"pid": "1", "pos": "DEF", "name": "Hancko", "pts": 10, "when": None, "gone": None},
                  {"pid": "2", "pos": "POR", "name": "Soria", "pts": None, "when": datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc),
                   "vs": "vs Rayo", "gone": None},
                  {"pid": "3", "pos": "CEN", "name": "Giménez", "pts": 6, "when": None, "gone": "vendido · 16/10 21:01"},
                  {"pid": "4", "pos": "DEF", "name": "Yoel Lago", "pts": None, "when": None, "gone": "clausulado por Josinho · 17/10 23:14"}],
         "bench": [{"pid": "9", "pos": "POR", "name": "A. Herrero", "avg": 5.4, "status": "ok"},
                   {"pid": "8", "pos": "DEF", "name": "Salinas", "avg": 2.3, "status": "injured"}],
         "formation": [3, 5, 2], "missing": {"DEF": 2, "CEN": 5}, "sold": 0}

    def test_three_blocks_one_line_per_player_with_position_and_state_icons(self):
        b = panel.jornada_blocks(self.D, {"1": "Dávid Hancko"})
        self.assertEqual(b["once"][0], "🧤 Soria — ⏳ lun 19 21:00 · vs Rayo")
        self.assertIn("🛡️ Dávid Hancko — ✅ <b>10 pts</b>", b["once"])
        self.assertIn("🛡️ <i>2 hueco(s): ya no están</i>", b["once"])
        self.assertTrue(all(not l.startswith("<b>") for l in b["once"]))          # sin títulos metidos dentro del desplegable

    def test_out_of_the_eleven_with_average_and_injury_flag(self):
        b = panel.jornada_blocks(self.D)
        self.assertIn("🧤 A. Herrero — media 5,4", b["fuera"])
        self.assertIn("🛡️ Salinas — media 2,3 · ⚠️ injured", b["fuera"])

    def test_those_who_left_go_apart_with_how_and_their_points(self):
        b = panel.jornada_blocks(self.D)
        self.assertIn("🧠 Giménez — <b>6 pts</b> · vendido · 16/10 21:01", b["ya_no"])
        self.assertIn("🛡️ Yoel Lago — sin jugar · clausulado por Josinho · 17/10 23:14", b["ya_no"])
        self.assertIn("<i>Lo que puntuó antes de irse cuenta.</i>", b["ya_no"])
        self.assertFalse(any("Giménez" in l for l in b["once"]))

    def test_points_not_explained_by_any_row_are_shown(self):
        d = {"rows": [{"pid": "1", "pos": "DEF", "name": "Hancko", "pts": 10, "when": None, "gone": None}], "sold": 6}
        self.assertIn("+ 6 pts más", panel.jornada_blocks(d)["ya_no"][-1])

    def test_repeated_surnames_are_collapsed(self):
        self.assertEqual(panel.clean_name("Moriba Kourouma Kourouma"), "Moriba Kourouma")


class Results(unittest.TestCase):
    LINES = ["<b>📊 REVISIÓN</b>", "Patrimonio ahora: 301.19M (saldo 46.34M + plantilla 254.85M)",
             "Operaciones cerradas desde 2026-09-26: 30 · 19 con ganancia · resultado +22.12M", "  compradas por puja: 14 · -6.00M", "Puntos: 162"]

    def test_summary_visible_and_details_folded(self):
        text = panel.results_section(self.LINES)
        self.assertIn("30 operaciones · 19 con ganancia · +22,1M", text)
        self.assertIn("<blockquote expandable>💰 Patrimonio ahora: 301,2M", text)
        self.assertNotIn("Puntos: 162", text)

    def test_nothing_to_show_without_a_review(self):
        self.assertIsNone(panel.results_section(None))


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
