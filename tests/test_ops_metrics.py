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

    def test_content_bearing_telemetry_is_rejected(self):
        payload = {"schema_version": 1, "generated_at": "2026-10-14T21:00:00Z",
                   "interval": {"start": "2026-10-14T20:00:00Z", "end": "2026-10-14T21:00:00Z"},
                   "by_pane": [{"pane": "sample:p1", "body": "private message"}]}
        with self.assertRaisesRegex(ValueError, "content-bearing"):
            ops_metrics._valid_dunk_metrics(payload)
