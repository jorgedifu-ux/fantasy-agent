"""Bandeja de avisos: lo urgente sale ya, el resto en resúmenes a horas fijas."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fantasy_agent import inbox
from fantasy_agent.storage import Store


class Routing(unittest.TestCase):
    def test_what_prevents_playing_or_loses_a_player_is_urgent(self):
        urgent, info = inbox.split([
            "🔴 <b>Sigo en negativo</b> (faltan 3M)", "🚨 <b>Yoel Lago</b> ya no está en tu plantilla: te lo han clausulado.",
            "⚠️ No he podido guardar la alineación (reintento en 15 min)", "💰 <b>Vendido</b> Terrats por 20,9M",
            "🏷️ En venta (solo se vende si llega una buena oferta): Hancko", "🛒 Puja ganada"])
        self.assertEqual(len(urgent), 3)
        self.assertTrue(info[0].startswith("💰") and info[1].startswith("🛒") and len(info) == 2)      # lo de «en venta» no informa de nada

    def test_a_failed_step_alert_is_not_urgent(self):
        urgent, info = inbox.split(["⚠️ Pasos con error en esta pasada (el resto se hizo): comandos: algo"])
        self.assertEqual((urgent, len(info)), ([], 1))


class Digest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def test_nothing_pending_means_nothing_due(self):
        self.assertFalse(inbox.digest_due(self.store, datetime(2026, 10, 18, 14, 5)))

    def test_it_is_due_once_per_slot_and_then_waits_for_the_next(self):
        inbox.add(self.store, ["💰 Vendido A"], now=datetime(2026, 10, 18, 8, 30).timestamp())
        self.assertTrue(inbox.digest_due(self.store, datetime(2026, 10, 18, 9, 1)))
        self.assertIn("Vendido A", inbox.flush_text(self.store, datetime(2026, 10, 18, 9, 1)))
        inbox.add(self.store, ["💰 Vendido B"], now=datetime(2026, 10, 18, 10, 0).timestamp())
        self.assertFalse(inbox.digest_due(self.store, datetime(2026, 10, 18, 13, 59)))
        self.assertTrue(inbox.digest_due(self.store, datetime(2026, 10, 18, 14, 0)))

    def test_during_the_night_it_waits_for_the_nine(self):
        inbox.add(self.store, ["💰 Vendido A"], now=datetime(2026, 10, 18, 1, 31).timestamp())
        inbox.clear(self.store, now=datetime(2026, 10, 17, 22, 0).timestamp())
        inbox.add(self.store, ["💰 Vendido A"], now=datetime(2026, 10, 18, 1, 31).timestamp())
        self.assertFalse(inbox.digest_due(self.store, datetime(2026, 10, 18, 2, 0)))
        self.assertTrue(inbox.digest_due(self.store, datetime(2026, 10, 18, 9, 0)))

    def test_the_digest_groups_dedupes_and_keeps_only_the_last_lineup(self):
        items = [{"t": 1, "text": x} for x in (
            "💰 Vendido A", "💰 Vendido A", "🛒 Fichado B", "🧩 Alineación guardada 3-4-3", "🧩 Alineación guardada 4-4-2",
            "❌ Puja perdida: C")]
        text = inbox.render_digest(items, now=datetime(2026, 10, 18, 9, 0))
        self.assertEqual(text.count("Vendido A"), 1)
        self.assertIn("4-4-2", text)
        self.assertNotIn("3-4-3", text)
        self.assertIn("Ventas", text)
        self.assertIn("Fichajes", text)


if __name__ == "__main__":
    unittest.main()
