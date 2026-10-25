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
        row["measured_at"] -= 4000
        row["windows"][0]["resets_at"] = (NOW - timedelta(seconds=1)).isoformat()
        provider = self.project([row])["providers"][0]
        self.assertEqual("stale", provider["state"])
        self.assertEqual("expired", provider["windows"][0]["state"])

    def test_ten_minute_old_collector_snapshot_keeps_number_and_age(self):
        row = dict(provider="codex", status="unknown", meaning="percent_used",
                   measured_at=(NOW - timedelta(minutes=10)).timestamp(),
                   reason="no live account endpoint", last_snapshot=dict(
                       percent_used=33, window_minutes=10080,
                       resets_at=(NOW + timedelta(days=4)).timestamp()))
        provider = self.project([row])["providers"][0]
        self.assertEqual("ok", provider["state"])
        self.assertEqual(600, provider["age_s"])
        self.assertEqual(33, provider["windows"][0]["percent_used"])
        self.assertEqual(67, provider["windows"][0]["percent_remaining"])
        self.assertEqual("weekly", provider["windows"][0]["name"])
        self.assertEqual("2026-10-25T03:50:00Z", provider["measured_at"])

    def test_upstream_error_is_named_and_has_a_check_age(self):
        row = dict(provider="claude", status="error", meaning="unknown",
                   measured_at=(NOW - timedelta(seconds=20)).timestamp(),
                   error='usage endpoint HTTP 429: rate_limit_error')
        provider = self.project([row])["providers"][0]
        self.assertEqual("claude endpoint rate-limited (HTTP 429)", provider["reason"])
        self.assertEqual(20, provider["age_s"])
        self.assertEqual([], provider["windows"])
        row["error"] = ""
        self.assertIn("no further reason supplied", self.project([row])["providers"][0]["reason"])

    def test_old_pi_values_remain_local_estimates(self):
        row = dict(provider="pi", status="unknown", meaning="local_session_estimate",
                   measured_at=(NOW - timedelta(minutes=10)).timestamp(), session_cost_usd=1.5)
        provider = self.project([row])["providers"][0]
        self.assertEqual("ok", provider["state"])
        self.assertEqual(600, provider["age_s"])
        self.assertEqual(1.5, provider["local_estimate"]["session_cost_usd"])
        self.assertEqual([], provider["windows"])

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

    def test_partial_command_failure_keeps_named_provider_error(self):
        import json
        from types import SimpleNamespace
        row = dict(provider="claude", status="error", error="HTTP 429", windows=[])
        command = SimpleNamespace(returncode=1, stdout=json.dumps([row]), stderr="one provider unavailable")
        with patch.object(ops_budget.subprocess, "run", return_value=command):
            self.assertEqual(row, ops_budget._read_provider("claude"))

    def test_all_providers_share_floor_and_failure_backoff(self):
        clock = [NOW.timestamp()]
        calls = []
        def reader(provider):
            calls.append(provider)
            if clock[0] > NOW.timestamp():
                return dict(provider=provider, status="error", meaning="unknown", error="HTTP 429", measured_at=clock[0])
            return reading(provider)
        cache = ops_budget.UsageCache(refresh_s=1800, backoff_s=(300,600,1800), reader=reader, clock=lambda: clock[0])
        self.addCleanup(cache.stop)
        def settle():
            cache.snapshot()
            for future in list(cache._futures.values()):
                future.result(timeout=3)
            return cache.snapshot()
        self.assertEqual(4, len(settle()))
        self.assertCountEqual(ops_budget.PROVIDERS, calls)
        clock[0] += 720
        settle()
        self.assertEqual(4, len(calls), "a second build inside the floor must not reread providers")
        clock[0] = NOW.timestamp()+1800
        rows = settle()
        self.assertEqual(8, len(calls))
        claude = next(r for r in rows if r["provider"] == "claude")
        self.assertEqual(clock[0]+300, claude["next_attempt_at"])
        provider = ops_budget.project([claude], [], NOW + timedelta(seconds=1800))["providers"][0]
        self.assertTrue(provider["last_good"])
        self.assertEqual(31, provider["windows"][0]["percent_used"])
        self.assertEqual(1800, provider["age_s"])
        self.assertNotEqual(provider["failed_at"], provider["measured_at"])
        self.assertEqual("claude endpoint rate-limited (HTTP 429)", provider["reason"])
        for delay in (300,600,1800):
            clock[0] = claude["next_attempt_at"]
            rows = settle()
            claude = next(r for r in rows if r["provider"] == "claude")
            expected = 600 if delay==300 else 1800
            self.assertEqual(clock[0]+expected, claude["next_attempt_at"])

    def test_pending_first_read_and_first_429_are_distinct(self):
        import threading
        release = threading.Event()
        def reader(provider):
            release.wait(3)
            return dict(provider=provider, status="error", meaning="unknown", error="HTTP 429", measured_at=NOW.timestamp())
        cache = ops_budget.UsageCache(reader=reader)
        try:
            rows = cache.snapshot()
            self.assertTrue(all(row["status"]=="not_read_yet" for row in rows))
            release.set()
            for future in list(cache._futures.values()):
                future.result(timeout=3)
            provider = self.project(cache.snapshot())["providers"][0]
            self.assertEqual([], provider["windows"])
            self.assertFalse(provider["last_good"])
            self.assertEqual("claude endpoint rate-limited (HTTP 429)", provider["reason"])
        finally:
            release.set()
            cache.stop()

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
