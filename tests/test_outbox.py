"""Cortes pasajeros de Telegram: no avisan y no pierden el parte."""
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fantasy_agent import cli
from fantasy_agent.storage import Store


class TransientErrors(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def test_a_timeout_is_logged_but_does_not_alert(self):
        errs = []

        def boom():
            raise TimeoutError("The read operation timed out")
        cli._step(self.store, errs, "telegram", boom)
        self.assertEqual(errs, [])
        self.assertEqual(self.store.errors()[-1]["step"], "telegram")

    def test_a_real_error_still_alerts(self):
        errs = []

        def boom():
            raise ValueError("algo falla de verdad")
        cli._step(self.store, errs, "alineación", boom)
        self.assertEqual(len(errs), 1)

    def test_a_failed_send_is_kept_and_resent_with_the_next_one(self):
        with mock.patch.object(cli.notify, "send_all", side_effect=TimeoutError("read operation timed out")):
            with self.assertRaises(TimeoutError):
                cli._send_or_queue(self.store, SimpleNamespace(), "vendido Terrats")
        self.assertIn("vendido Terrats", self.store.get("outbox"))
        sent = []
        with mock.patch.object(cli.notify, "send_all", side_effect=lambda s, text, **k: sent.append(text)):
            cli._send_or_queue(self.store, SimpleNamespace(), "puja ganada")
        self.assertIn("vendido Terrats", sent[0])
        self.assertIn("puja ganada", sent[0])
        self.assertEqual(self.store.get("outbox"), "")

    def test_nothing_to_send_does_nothing(self):
        with mock.patch.object(cli.notify, "send_all") as m:
            cli._send_or_queue(self.store, SimpleNamespace(), "")
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
