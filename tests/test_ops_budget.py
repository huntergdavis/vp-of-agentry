"""Allowance windows never become inferred dollars or invented zeroes."""
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import ops_budget
import ops_metrics

NOW = datetime(2026, 10, 25, 4, tzinfo=timezone.utc)


def reading(provider="codex", **extra):
    return dict(provider=provider, meaning="percent_used", status="ok",
                measured_at=NOW.timestamp(), windows=[
                    dict(name="weekly", percent_used=31, percent_remaining=69,
                         resets_at=(NOW + timedelta(days=4)).timestamp())], **extra)


class BudgetTests(unittest.TestCase):
    def project(self, rows, prices=()):
        return ops_budget.project(rows, prices, NOW)

    def test_preserves_provider_windows_and_epoch_reset(self):
        provider = self.project([reading()])["providers"][0]
        self.assertEqual("weekly", provider["windows"][0]["name"])
        self.assertEqual(69, provider["windows"][0]["percent_remaining"])
        self.assertEqual("2026-10-29T04:00:00Z", provider["windows"][0]["resets_at"])
        self.assertEqual("ok", provider["state"])
        self.assertTrue(provider["measured_at"])
        self.assertEqual(ops_budget.SOURCE, provider["source"])

    def test_empty_windows_and_missing_provider_stay_unknown(self):
        row = reading()
        row["windows"] = []
        price = dict(provider="claude", monthly_usd_cents=20000, observed_at="2026-10-01T00:00:00Z")
        result = self.project([row], [price])
        self.assertEqual([], result["providers"][0]["windows"])
        self.assertEqual("unavailable", result["providers"][1]["state"])
        self.assertIsNone(result["dollars_remaining"])

    def test_pi_estimate_is_not_a_quota_and_credits_are_not_dollars(self):
        row = reading("pi")
        row.update(meaning="local_session_estimate", session_cost_usd=1.65)
        self.assertEqual([], self.project([row])["providers"][0]["windows"])
        self.assertEqual(1.65, self.project([row])["providers"][0]["local_estimate"]["session_cost_usd"])
        extra = dict(used_credits=90154, monthly_limit=90000, utilization=100, spend_limit_reached=False)
        result = self.project([reading("claude", extra_usage=extra)])
        self.assertEqual(extra, result["providers"][0]["extra_usage"])
        self.assertIsNone(result["dollars_remaining"])

    def test_stale_and_expired_are_labelled(self):
        row = reading()
        row["measured_at"] -= 600
        row["windows"][0]["resets_at"] = (NOW - timedelta(seconds=1)).isoformat()
        provider = self.project([row])["providers"][0]
        self.assertEqual("stale", provider["state"])
        self.assertEqual("expired", provider["windows"][0]["state"])

    def test_unknown_values_are_not_zero_and_nonfinite_is_rejected(self):
        row = reading()
        row["windows"][0].update(percent_used=float("nan"), percent_remaining=None)
        window = self.project([row])["providers"][0]["windows"][0]
        self.assertIsNone(window["percent_used"])
        self.assertIsNone(window["percent_remaining"])
        self.assertEqual("unknown", window["state"])

    def test_subscription_is_separate_and_alias_matches_go(self):
        price = dict(provider="opencode", monthly_usd_cents=4000, observed_at="2026-10-01T00:00:00Z")
        result = self.project([reading("opencode-go")], [price])
        self.assertEqual(1, len(result["providers"]))
        self.assertEqual(40, result["providers"][0]["subscription"]["monthly_usd"])
        self.assertEqual(69, result["providers"][0]["windows"][0]["percent_remaining"])

    def test_partial_command_failure_keeps_other_providers(self):
        import json
        from types import SimpleNamespace
        rows = [reading("claude"), dict(provider="codex", status="error", windows=[])]
        command = SimpleNamespace(returncode=1, stdout=json.dumps(rows), stderr="one provider unavailable")
        with patch.object(ops_budget.subprocess, "run", return_value=command):
            self.assertEqual(rows, ops_budget.read_usage())

    def test_command_failure_preserves_unknown_and_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = ops_metrics.connect(Path(tmp) / "ops.db")
            self.addCleanup(conn.close)
            conn.execute("INSERT INTO subscription_costs(project,provider,monthly_usd_cents,observed_at,evidence_ref) VALUES(?,?,?,?,?)",
                         (ops_metrics.PROJECT, "claude", 20000, NOW.isoformat(), "test"))
            conn.commit()
            with patch.object(ops_budget, "read_usage", side_effect=subprocess.TimeoutExpired("usage", 20)):
                budget = ops_budget.build(conn, NOW)
        self.assertEqual("unavailable", budget["state"])
        self.assertEqual([], budget["providers"][0]["windows"])
        self.assertEqual(200, budget["providers"][0]["subscription"]["monthly_usd"])
