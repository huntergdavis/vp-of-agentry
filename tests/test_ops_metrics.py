"""Operations metrics retain provenance and distinguish missing data from zero."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import ops_metrics


class OpsMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.conn = ops_metrics.connect(Path(self.temporary.name) / "ops.sqlite3")
        self.addCleanup(self.conn.close)

    def test_missing_telemetry_stays_unavailable(self):
        def command(argv, **_):
            if argv[0] == "dunkingsheep" and "panes" in argv:
                return {"panes": [{"pane_id": "sample:p1", "workspace_label": "poolrad-decomp",
                                   "agent_status": "working"}]}
            if argv[0] == "gh":
                return []
            raise RuntimeError("telemetry not installed")

        with patch.object(ops_metrics, "command_json", side_effect=command), \
             patch.object(ops_metrics, "_vp_counts", return_value=[("vp", "owner", 2)]):
            result = ops_metrics.collect(
                self.conn, now=datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
            )
            later = ops_metrics.collect(
                self.conn, now=datetime(2026, 10, 14, 21, 1, tzinfo=timezone.utc)
            )
        self.assertEqual(result["sources"]["dunk_metrics"], "unavailable")
        self.assertIsNone(result["dunk_metrics"])
        self.assertEqual(result["staff"]["other"]["working"], 1)
        self.assertIsNone(result["quota"])
        self.assertEqual(result["quotas"], {"codex": None, "claude": None})
        self.assertEqual(later["sources"]["github"], "cached")
        self.assertEqual(later["source_freshness"]["github"]["age_s"], 60)
        self.assertIsNone(later["source_freshness"]["dunk_metrics"]["last_ok_at"])

    def test_burn_requires_same_reset_and_elapsed_time(self):
        ops_metrics.record_quota(
            self.conn, pane="sample:p1", percent_left=40, reset_at="2026-10-21T20:00:00Z",
            observed_at="2026-10-14T20:00:00Z", evidence="direct status A"
        )
        ops_metrics.record_quota(
            self.conn, pane="sample:p1", percent_left=38, reset_at="2026-10-21T20:00:00Z",
            observed_at="2026-10-14T21:00:00Z", evidence="direct status B"
        )
        result = ops_metrics.summary(
            self.conn, now=datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(result["quota"]["burn_percentage_points_per_hour"], 2)
        self.assertEqual(result["quota"]["weekly_percent_left"], 38)

    def test_provider_quota_readings_stay_separate(self):
        ops_metrics.record_quota(
            self.conn, pane="codex:p1", percent_left=91, reset_at="2026-10-23T14:49:00Z",
            observed_at="2026-10-16T16:49:00Z", evidence="direct Codex status",
        )
        ops_metrics.record_quota(
            self.conn, pane="claude:p1", percent_left=80, reset_at="2026-10-22T14:00:00Z",
            observed_at="2026-10-16T17:00:00Z", evidence="direct Claude status",
            provider="claude",
        )
        result = ops_metrics.summary(
            self.conn, now=datetime(2026, 10, 16, 17, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(result["quotas"]["codex"]["weekly_percent_left"], 91)
        self.assertEqual(result["quotas"]["claude"]["weekly_percent_left"], 80)
        self.assertEqual(result["quotas"]["claude"]["cohort"], "poolrad-claude")
        self.assertIsNone(result["quotas"]["claude"]["burn_percentage_points_per_hour"])
        self.assertEqual(result["quota"]["provider"], "claude")

    def test_history_uses_recorded_events_without_filling_gaps(self):
        with self.conn:
            run = self.conn.execute(
                "INSERT INTO collection_runs(observed_at,panes_state,github_state,vp_messages_state,dunk_metrics_state,errors_json) "
                "VALUES(?,?,?,?,?,?)",
                ("2026-10-14T21:00:00Z", "ok", "ok", "ok", "unavailable", "{}"),
            ).lastrowid
            self.conn.execute(
                "INSERT INTO pane_samples(run_id,pane_id,project,agent_status,role) VALUES(?,?,?,?,?)",
                (run, "sample:p1", "poolrad", "working", "coder"),
            )
            self.conn.execute(
                "INSERT INTO pr_latest(project,number,state,head_oid,merged_at,first_seen_at,last_seen_at) "
                "VALUES(?,?,?,?,?,?,?)",
                ("poolrad", 123, "MERGED", "abc", "2026-10-14T21:15:00Z",
                 "2026-10-14T20:00:00Z", "2026-10-14T21:30:00Z"),
            )
        ops_metrics.record_goal(
            self.conn, key="strict_fullc", scope="local", status="verified", value=71,
            target=None, unit="functions", evidence="PM reviewed checkpoint",
            note="", observed_at="2026-10-14T21:30:00Z",
        )
        result = ops_metrics.history(
            self.conn, now=datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(len(result["coder_samples"]), 1)
        self.assertEqual(result["coder_samples"][0]["working"], 1)
        self.assertEqual(result["pr_merges"][0]["merged_at"], "2026-10-14T21:15:00Z")
        self.assertEqual(result["goal_observations"][0]["value"], 71)

    def test_content_bearing_telemetry_is_rejected(self):
        payload = {"schema_version": 1, "generated_at": "2026-10-14T21:00:00Z",
                   "interval": {"start": "2026-10-14T20:00:00Z", "end": "2026-10-14T21:00:00Z"},
                   "by_pane": [{"pane": "sample:p1", "body": "private message"}]}
        with self.assertRaisesRegex(ValueError, "content-bearing"):
            ops_metrics._valid_dunk_metrics(payload)

    def test_unix_second_telemetry_timestamps_are_normalized(self):
        payload = {"schema_version": 1, "generated_at": 1792011600,
                   "interval": {"start": 1792008000.0, "end": 1792011600},
                   "units": {"timestamp": "unix_epoch_seconds"}, "counts": {}}
        result = ops_metrics._valid_dunk_metrics(payload)
        self.assertEqual(result["generated_at"], 1792011600)
        self.assertEqual(ops_metrics._dunk_timestamp(result["generated_at"], "generated_at"),
                         "2026-10-14T21:00:00Z")
        self.assertEqual(ops_metrics._dunk_timestamp(result["interval"]["start"], "interval.start"),
                         "2026-10-14T20:00:00Z")

    def test_manual_refresh_repolls_external_sources(self):
        calls = []
        def command(argv, **_):
            calls.append(argv)
            if argv[0] == "gh":
                return []
            if "panes" in argv:
                return {"panes": []}
            return {"schema_version": 1, "generated_at": 1792011600,
                    "interval": {"start": 1792008000, "end": 1792011600},
                    "counts": {"events": 0}}

        with patch.object(ops_metrics, "command_json", side_effect=command), \
             patch.object(ops_metrics, "_vp_counts", return_value=[]):
            ops_metrics.collect(self.conn, now=datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc))
            result = ops_metrics.collect(
                self.conn, now=datetime(2026, 10, 14, 21, 1, tzinfo=timezone.utc),
                force_external=True
            )
        self.assertEqual(result["sources"]["github"], "ok")
        self.assertEqual(result["sources"]["dunk_metrics"], "ok")
        self.assertEqual(sum(argv[0] == "gh" for argv in calls), 2)
        self.assertEqual(sum("metrics" in argv for argv in calls), 2)

    def test_owner_subscription_history_gives_fixed_total_only(self):
        ops_metrics.record_subscription(
            self.conn, provider="claude", monthly_usd="10.00", evidence="owner report A"
        )
        ops_metrics.record_subscription(
            self.conn, provider="codex", monthly_usd="20", evidence="owner report B"
        )
        ops_metrics.record_subscription(
            self.conn, provider="claude", monthly_usd="12.00", evidence="owner update"
        )
        result = ops_metrics.summary(self.conn)
        self.assertEqual(result["monthly_fixed_usd"], 32)
        self.assertIsNone(result["usage_cost_usd"])
        self.assertEqual(len(result["subscriptions"]), 2)
        with self.assertRaisesRegex(ValueError, "two decimal places"):
            ops_metrics.record_subscription(
                self.conn, provider="codex", monthly_usd="1.001", evidence="invalid"
            )
