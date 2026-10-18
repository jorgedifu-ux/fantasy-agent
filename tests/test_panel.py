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
                  {"pid": "2", "pos": "POR", "name": "Soria", "pts": None, "when": datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc), "gone": None},
                  {"pid": "3", "pos": "CEN", "name": "Giménez", "pts": 6, "when": None, "gone": "vendido · 16/10 21:01"},
                  {"pid": "4", "pos": "DEF", "name": "Yoel Lago", "pts": None, "when": None, "gone": "clausulado por Josinho · 17/10 23:14"}],
         "sold": 0}

    def test_grouped_by_position_with_a_state_icon(self):
        text = "\n".join(panel.jornada_lines(self.D, {"1": "Dávid Hancko"}))
        self.assertIn("<b>🧤 Portero</b>\n⏳ Soria — lun", text)
        self.assertIn("<b>🛡️ Defensas</b>\n✅ Dávid Hancko — <b>10 pts</b>", text)

    def test_those_who_left_go_apart_with_how_and_their_points(self):
        text = "\n".join(panel.jornada_lines(self.D))
        self.assertIn("<b>🚪 Ya no están</b>", text)
        self.assertIn("Giménez (CEN) — <b>6 pts</b> · vendido · 16/10 21:01", text)
        self.assertIn("Yoel Lago (DEF) — sin jugar · clausulado por Josinho", text)
        self.assertNotIn("Giménez — <b>6 pts</b>\n", text.split("Ya no están")[0])      # no sale entre los de la plantilla

    def test_points_not_explained_by_any_row_are_shown(self):
        d = {"rows": [{"pid": "1", "pos": "DEF", "name": "Hancko", "pts": 10, "when": None, "gone": None}], "sold": 6}
        self.assertIn("+ 6 pts más", panel.jornada_lines(d)[-1])


class JornadaDetail(unittest.TestCase):
    def test_who_is_in_the_eleven_who_is_out_and_the_holes(self):
        d = {"rows": [{"pid": "1", "pos": "DEF", "name": "Hancko", "pts": 10, "when": None, "gone": None},
                      {"pid": "2", "pos": "POR", "name": "Soria", "pts": None, "when": datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc),
                       "vs": "vs Rayo", "gone": None}],
             "bench": [{"pid": "9", "pos": "POR", "name": "A. Herrero", "avg": 5.4, "status": "ok"},
                       {"pid": "8", "pos": "DEF", "name": "Salinas", "avg": 2.3, "status": "injured"}],
             "formation": [3, 5, 2], "missing": {"DEF": 2, "CEN": 5, "DEL": 2}, "sold": 0}
        text = "\n".join(panel.jornada_lines(d))
        self.assertIn("🧩 Tu once (3-5-2)</b> · 2 de 11 siguen contigo", text)
        self.assertIn("⏳ Soria — lun 19 21:00 · vs Rayo", text)
        self.assertIn("… 2 hueco(s)", text)
        self.assertIn("🪑 Fuera del once</b> (no puntúan)", text)
        self.assertIn("A. Herrero (POR) — media 5,4", text)
        self.assertIn("Salinas (DEF) — media 2,3 · ⚠️ injured", text)

    def test_repeated_surnames_are_collapsed(self):
        self.assertEqual(panel.clean_name("Moriba Kourouma Kourouma"), "Moriba Kourouma")


class Results(unittest.TestCase):
    LINES = ["<b>📊 REVISIÓN</b>", "Patrimonio ahora: 301.19M (saldo 46.34M + plantilla 254.85M)",
             "Operaciones cerradas desde 2026-09-26: 30 · 19 con ganancia · resultado +22.12M", "  compradas por puja: 14 · -6.00M", "Puntos: 162"]

    def test_summary_visible_and_details_folded(self):
        text = panel.results_section(self.LINES)
        self.assertIn("30 operaciones · 19 con ganancia · +22.12M", text)
        self.assertIn("<blockquote expandable>Patrimonio ahora", text)
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
