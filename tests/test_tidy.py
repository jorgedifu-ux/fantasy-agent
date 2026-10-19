"""Orden del chat (se borra lo viejo menos el panel) y escucha de órdenes."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fantasy_agent import commands, notify, tidy
from fantasy_agent.storage import Store


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "s.db")
        notify.SENT_IDS.clear()

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()


class Sweep(Base):
    def test_old_messages_are_deleted_and_recent_ones_kept(self):
        now = time.time()
        tidy.track(self.store, [1], now=now - 25 * 3600)
        tidy.track(self.store, [2], now=now - 3600)
        gone = []
        n = tidy.sweep(self.store, SimpleNamespace(), now=now, delete=lambda mid: gone.append(mid) or True)
        self.assertEqual((n, gone), (1, [1]))
        self.assertEqual([i["id"] for i in json.loads(self.store.get("sent_msgs"))], [2])

    def test_the_pinned_panel_is_never_deleted(self):
        self.store.set("panel_message_id", "7")
        now = time.time()
        notify.SENT_IDS.extend([7, 8])           # el panel y otro mensaje, mandados en esta pasada
        gone = []
        tidy.sweep(self.store, SimpleNamespace(), now=now, delete=lambda mid: gone.append(mid) or True)
        self.assertEqual(gone, [])
        tidy.sweep(self.store, SimpleNamespace(), now=now + 25 * 3600, delete=lambda mid: gone.append(mid) or True)
        self.assertEqual(gone, [8])               # el otro se borra a las 24 h; el panel, nunca

    def test_what_was_sent_this_pass_is_tracked_for_later(self):
        notify.SENT_IDS.extend([10, 11])
        tidy.sweep(self.store, SimpleNamespace(), now=time.time(), delete=lambda mid: True)
        self.assertEqual(sorted(i["id"] for i in json.loads(self.store.get("sent_msgs"))), [10, 11])
        self.assertEqual(notify.SENT_IDS, [])

    def test_a_failed_delete_is_retried_next_time(self):
        tidy.track(self.store, [5], now=time.time() - 30 * 3600)
        self.assertEqual(tidy.sweep(self.store, SimpleNamespace(), delete=lambda mid: False), 0)
        self.assertEqual(len(json.loads(self.store.get("sent_msgs"))), 1)


class Listen(Base):
    def settings(self):
        return SimpleNamespace(telegram_token="t", telegram_chat_id="42")

    def test_it_answers_my_chat_and_ignores_strangers(self):
        updates = [
            {"update_id": 1, "message": {"message_id": 100, "chat": {"id": 42}, "text": "/ayuda"}},
            {"update_id": 2, "message": {"message_id": 101, "chat": {"id": 99}, "text": "/ayuda"}},
        ]
        sent = []
        with mock.patch.object(notify, "send_all", side_effect=lambda s, text, **k: sent.append(text)):
            commands._handle(self.settings(), self.store, None, None, updates)
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.store.get("telegram_last_update_id"), "2")
        self.assertIsNotNone(self.store.get("last_user_at"))

    def test_my_order_is_scheduled_for_deletion_in_an_hour(self):
        updates = [{"update_id": 1, "message": {"message_id": 100, "chat": {"id": 42}, "text": "/ayuda"}}]
        with mock.patch.object(notify, "send_all"):
            commands._handle(self.settings(), self.store, None, None, updates)
        item = json.loads(self.store.get("sent_msgs"))[0]
        self.assertEqual(item["id"], 100)
        self.assertLess(item["due"] - time.time(), 3700)

    def test_listen_polls_until_the_deadline_and_answers_what_arrives(self):
        calls = []

        def fake_updates(settings, offset=None, wait=0):
            calls.append(wait)
            return [{"update_id": 5, "message": {"message_id": 1, "chat": {"id": 42}, "text": "/ayuda"}}] if len(calls) == 1 else []
        with mock.patch.object(notify, "get_telegram_updates", side_effect=fake_updates), \
                mock.patch.object(notify, "send_all") as sent, mock.patch.object(commands.time, "time", side_effect=[0, 0, 0, 0, 1000, 1000]):
            n = commands.listen(self.settings(), self.store, None, None, until=60, wait=25)
        self.assertEqual(n, 1)
        self.assertEqual(sent.call_count, 1)


if __name__ == "__main__":
    unittest.main()


class Purge(Base):
    def test_purge_deletes_tracked_and_untracked_ids_but_not_the_pinned_panel(self):
        self.store.set("panel_message_id", "50")
        tidy.track(self.store, [58], now=time.time())
        gone = []
        n = tidy.purge(self.store, SimpleNamespace(), delete=lambda mid: gone.append(mid) or True, latest=60, pinned=50)
        self.assertNotIn(50, gone)
        self.assertIn(58, gone)
        self.assertIn(60, gone)           # el mensaje de prueba también
        self.assertEqual(len(gone), len(set(gone)))
        self.assertEqual(n, len(gone))
        self.assertEqual(json.loads(self.store.get("sent_msgs")), [])

    def test_the_pinned_message_reported_by_telegram_is_respected_even_if_not_known(self):
        gone = []
        tidy.purge(self.store, SimpleNamespace(), delete=lambda mid: gone.append(mid) or True, latest=20, pinned=15)
        self.assertNotIn(15, gone)
        self.assertIn(16, gone)


class PurgeKeepsUnread(Base):
    def test_purge_leaves_urgent_messages_that_were_not_read(self):
        tidy.track(self.store, [2], now=time.time())
        tidy.track(self.store, [3], now=time.time(), keep=True)
        gone = []
        tidy.purge(self.store, SimpleNamespace(), delete=lambda mid: gone.append(mid) or True, latest=3, pinned=1)
        self.assertIn(2, gone)
        self.assertNotIn(3, gone)
        self.assertEqual([i["id"] for i in json.loads(self.store.get("sent_msgs"))], [3])

    def test_the_ttl_sweep_still_deletes_them_when_due(self):
        tidy.track(self.store, [3], now=time.time() - 30 * 3600, keep=True)
        gone = []
        tidy.sweep(self.store, SimpleNamespace(), delete=lambda mid: gone.append(mid) or True)
        self.assertEqual(gone, [3])
