"""Tests sin red de la exportación del estado (ver export.py)."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fantasy_agent import cli, export
from fantasy_agent.config import Settings
from fantasy_agent.storage import Store


def fresh():
    return Store(Path(tempfile.mkdtemp()) / "t.db")


class RoundTripTests(unittest.TestCase):
    def test_state_survives_export_and_import(self):
        a = fresh()
        a.log_offer("o1", "p1", "Koski", 28_000_000, 28_970_000, True, ask=30_000_000, listed_value=27_000_000)
        a.add_market_bid("p2", "Yuri", 19_000_000, None, ask=18_500_000)
        a.log_purchase("p2", "inversion", 19_000_000)
        a.log_wealth("2026-10-05", 29_000_000, 224_000_000)
        a.set_params({"league_offer_min": 1.06})
        a.log_proposal({"league_offer_min": {"old": 1.05, "new": 1.06, "why": "prueba"}})
        state = json.loads(json.dumps(export.build_state(a)))        # como viajaría por internet
        b = fresh()
        b.import_state(state)
        self.assertEqual(b.offer_rows()[0]["ask"], 30_000_000)
        self.assertEqual(b.purchases()[0]["origin"], "inversion")
        self.assertEqual(b.wealth_first(), ("2026-10-05", 29_000_000, 224_000_000))
        self.assertEqual(b.get_params()["league_offer_min"], 1.06)
        self.assertEqual(b.proposals()[0]["changes"]["league_offer_min"]["new"], 1.06)

    def test_the_export_never_contains_secrets(self):
        a = fresh()
        a.set("telegram_last_update_id", "12345")
        a.set("team_plan", "{}")
        dumped = json.dumps(export.build_state(a))
        self.assertNotIn("telegram", dumped)
        self.assertNotIn("team_plan", dumped)


class PublishTests(unittest.TestCase):
    def run_publish(self, branch_exists=True, file_exists=True):
        calls = []

        def fake(method, url, headers=None, json_body=None, **kw):
            calls.append((method, url.split("api.github.com")[-1], json_body))
            if method == "GET" and "/git/ref/heads/data" in url and not branch_exists:
                raise RuntimeError("404")
            if method == "GET" and "/git/ref/heads/main" in url:
                return {"object": {"sha": "abc123"}}
            if method == "GET" and "/contents/" in url:
                if not file_exists:
                    raise RuntimeError("404")
                return {"sha": "oldsha"}
            return {}

        with patch("fantasy_agent.export.request_json", side_effect=fake):
            msg = export.publish({"meta": {"generated_at": "t"}, "tables": {}, "kv": {}}, token="T", repo="o/r")
        return calls, msg

    def test_updates_the_existing_file(self):
        calls, _ = self.run_publish()
        put = [c for c in calls if c[0] == "PUT"][0]
        self.assertEqual(put[2]["branch"], "data")
        self.assertEqual(put[2]["sha"], "oldsha")
        self.assertEqual(json.loads(base64.b64decode(put[2]["content"]))["meta"]["generated_at"], "t")

    def test_creates_the_branch_and_the_file_when_missing(self):
        calls, _ = self.run_publish(branch_exists=False, file_exists=False)
        post = [c for c in calls if c[0] == "POST"][0]
        self.assertEqual(post[2], {"ref": "refs/heads/data", "sha": "abc123"})
        put = [c for c in calls if c[0] == "PUT"][0]
        self.assertNotIn("sha", put[2])


class GatingTests(unittest.TestCase):
    def settings(self, export_data=True):
        import tempfile as tf
        return Settings(data_dir=Path(tf.mkdtemp()), league_id=None, team_id=None, telegram_token=None, telegram_chat_id=None,
                        clause_window_hours=24, watch_interval_min=30, report_hour=9, request_delay_s=0, briefing_interval_min=90,
                        budget_reserve_pct=0.05, lineup_lock_hours=24, debt_ceiling_pct=0.2, debt_min_hours_lead=36,
                        export_data=export_data)

    def test_does_nothing_without_a_token(self):
        with patch.dict("os.environ", {}, clear=True), patch("fantasy_agent.export.publish") as pub:
            self.assertEqual(cli._publish_state(fresh(), self.settings()), [])
            pub.assert_not_called()

    def test_publishes_once_per_six_hour_window(self):
        env = {"GITHUB_TOKEN": "T", "GITHUB_REPOSITORY": "o/r"}
        store = fresh()
        with patch.dict("os.environ", env, clear=True), patch("fantasy_agent.export.publish") as pub:
            cli._publish_state(store, self.settings())
            cli._publish_state(store, self.settings())
            self.assertEqual(pub.call_count, 1)

    def test_the_switch_disables_it(self):
        env = {"GITHUB_TOKEN": "T", "GITHUB_REPOSITORY": "o/r"}
        with patch.dict("os.environ", env, clear=True), patch("fantasy_agent.export.publish") as pub:
            cli._publish_state(fresh(), self.settings(export_data=False))
            pub.assert_not_called()

    def test_a_failure_never_raises_and_warns_once(self):
        env = {"GITHUB_TOKEN": "T", "GITHUB_REPOSITORY": "o/r"}
        with patch.dict("os.environ", env, clear=True), patch("fantasy_agent.export.publish", side_effect=RuntimeError("403")):
            out = cli._publish_state(fresh(), self.settings())
        self.assertEqual(len(out), 1)
        self.assertIn("403", out[0])


if __name__ == "__main__":
    unittest.main()
