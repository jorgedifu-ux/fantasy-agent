"""Tests sin red: serialización del plan, conservar lo añadido a mano, refresco semanal."""
import tempfile
import time
import unittest
from pathlib import Path

from fantasy_agent.plan import Plan, PlanItem, due_for_refresh, load_plan, render_plan_text, save_plan
from fantasy_agent.storage import Store


class PlanSerializationTests(unittest.TestCase):
    def test_roundtrip_preserves_items(self):
        plan = Plan(cash_reserve_note="20% de colchón")
        plan.targets.append(PlanItem(player_id="p1", player_name="Fulanito", reason="buen precio", priority="alta"))
        plan.watchlist.append(PlanItem(
            player_id="r1", player_name="Menganito", reason="cláusula barata", priority="alta",
            unlock_at=time.time() + 3600,
        ))
        restored = Plan.from_json(plan.to_json())
        self.assertEqual(restored.targets[0].player_name, "Fulanito")
        self.assertEqual(restored.watchlist[0].player_id, "r1")
        self.assertIsNotNone(restored.watchlist[0].unlock_at)


class RefreshTimingTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(Path(tempfile.mkdtemp()) / "t.sqlite3")

    def test_no_plan_yet_is_due(self):
        self.assertTrue(due_for_refresh(self.store))

    def test_fresh_plan_not_due(self):
        save_plan(self.store, Plan())
        self.assertFalse(due_for_refresh(self.store))

    def test_week_old_plan_is_due(self):
        plan = Plan()
        plan.updated_at = time.time() - 8 * 86400
        self.store.set("team_plan", plan.to_json())
        self.assertTrue(due_for_refresh(self.store))


class ManualPreservationTests(unittest.TestCase):
    def test_manual_items_marked_distinctly(self):
        plan = Plan()
        plan.targets.append(PlanItem(player_id="p1", player_name="Añadido a mano", reason="x", priority="alta", manual=True))
        restored = Plan.from_json(plan.to_json())
        self.assertTrue(restored.targets[0].manual)


class RenderTests(unittest.TestCase):
    def test_render_includes_all_sections(self):
        plan = Plan(cash_reserve_note="nota")
        plan.targets.append(PlanItem(player_id="p1", player_name="A", reason="r", priority="alta", max_price=1_000_000))
        text = render_plan_text(plan)
        self.assertIn("PLAN DE EQUIPO", text)
        self.assertIn("Fichajes objetivo", text)
        self.assertIn("Prioridad de venta", text)
        self.assertIn("Vigilando a rivales", text)
        self.assertIn("A", text)

    def test_render_escapes_player_names(self):
        plan = Plan()
        plan.targets.append(PlanItem(player_id="p1", player_name="A & B <script>", reason="r", priority="alta"))
        text = render_plan_text(plan)
        self.assertNotIn("<script>", text)
        self.assertIn("&amp;", text)


if __name__ == "__main__":
    unittest.main()
