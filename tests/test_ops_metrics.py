"""Operations metrics retain provenance and distinguish missing data from zero."""

import base64
import json
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
        source = patch.object(ops_metrics, "DUNK_EVENTS_DB", Path(self.temporary.name) / "missing-events.db")
        source.start()
        self.addCleanup(source.stop)
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

    def test_delivery_rows_use_agent_and_lane_names(self):
        def command(argv, **_):
            if argv[0] == "dunkingsheep" and "panes" in argv:
                return {"panes": [
                    {"pane_id": "sample:p1", "workspace_label": "poolrad-decomp",
                     "tab_label": "poolrad-codex-keyroute", "cwd": "/work/strict-c-a",
                     "agent": "codex", "agent_status": "working"},
                    {"pane_id": "sample:p2", "workspace_label": "poolrad-decomp",
                     "tab_label": "poolrad-codex-keyroute", "cwd": "/work/strict-c-b",
                     "agent": "codex", "agent_status": "working"},
                ]}
            if argv[0] == "gh":
                return []
            raise RuntimeError("telemetry not installed")

        with patch.object(ops_metrics, "command_json", side_effect=command), \
             patch.object(ops_metrics, "_vp_counts", return_value=[]):
            ops_metrics.collect(self.conn, now=datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc))
        with self.conn:
            self.conn.executemany(
                "INSERT INTO agent_message_events"
                "(source_event_id,occurred_at,pane_id,kind,delivery_source,mailbox_alias,source_ref) "
                "VALUES(?,?,?,?,?,?,?)",
                [(1, "2026-10-16T20:59:00Z", "sample:p1", "inbox.sent", "inbox", None, "test"),
                 (2, "2026-10-16T20:59:00Z", "sample:p2", "inbox.sent", "inbox", None, "test"),
                 (3, "2026-10-16T20:59:00Z", "sample:vp", "inbox.sent", "inbox", "VP of Agentry", "test")],
            )
        result = ops_metrics.summary(self.conn, now=datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc))
        rows = {row["pane_id"]: row for row in result["experiment_lab"]["messages_by_pane"]}
        self.assertEqual(rows["sample:p1"]["agent_name"], "poolrad-codex-keyroute")
        self.assertEqual(rows["sample:p1"]["lane_name"], "strict-c-a")
        self.assertEqual(rows["sample:p2"]["agent_name"], "poolrad-codex-keyroute")
        self.assertEqual(rows["sample:p2"]["lane_name"], "strict-c-b")
        self.assertEqual(rows["sample:vp"]["agent_name"], "VP of Agentry")

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
        self.assertEqual(sum(argv[:2] == ["gh", "pr"] for argv in calls), 2)
        self.assertEqual(sum("metrics" in argv for argv in calls), 2)

    def test_published_accounting_requires_matching_reviewed_sources(self):
        checkpoint = {"schema_version": 1, "strict_full_c_originals": 82,
                      "verified_game_identities": 143, "inputs": {"game": "same"}}
        census = {"status": "reviewed", "reviewed_by": "PM", "count": 815,
                  "bound_kind": "upper_bound",
                  "scope": "original-game-functions-overlay-and-resident",
                  "source_digests": {"game": "same"},
                  "evidence_doc": "docs/re/FUNCTION_CEILING_CENSUS.md"}
        def command(argv, **_):
            endpoint = argv[-1]
            if endpoint.endswith("/git/ref/heads/main"):
                return {"object": {"sha": "a" * 40}}
            content = checkpoint if "function_accounting_checkpoint" in endpoint else census
            return {"encoding": "base64", "content": base64.b64encode(json.dumps(content).encode()).decode()}
        with patch.object(ops_metrics, "command_json", side_effect=command):
            result = ops_metrics.published_accounting()
            self.assertEqual((result["strict_full_c"], result["ceiling"]), (82, 815))
            census["source_digests"] = {"game": "different"}
            with self.assertRaisesRegex(ValueError, "jointly reviewed"):
                ops_metrics.published_accounting()

    def test_hourly_cost_and_completion_rate_use_dated_comparable_snapshots(self):
        ops_metrics.record_subscription(self.conn, provider="codex", monthly_usd="200", evidence="owner")
        ops_metrics.record_subscription(self.conn, provider="claude", monthly_usd="200", evidence="owner")
        with self.conn:
            for at, strict, signature in (("2026-10-16T20:00:00Z", 82, "same"),
                                          ("2026-10-16T22:00:00Z", 83, "same")):
                self.conn.execute(
                    "INSERT INTO accounting_snapshots(project,observed_at,commit_oid,strict_full_c,"
                    "verified_game_identities,ceiling,bound_kind,source_signature,evidence_ref) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    ("poolrad", at, "a" * 40, strict, 143, 815, "upper_bound", signature, "reviewed census"),
                )
        result = ops_metrics.summary(self.conn, now=datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc))
        self.assertEqual(result["function_progress"]["strict_percent"], 10.1)
        self.assertEqual(result["completion_rate"]["delta_strict_functions"], 1)
        self.assertEqual(result["completion_rate"]["window_hours"], 2)
        self.assertAlmostEqual(result["completion_rate"]["function_coverage_points_per_hour"], 0.0613, places=4)
        self.assertEqual(result["calendar_hours_in_month"], 744)
        self.assertAlmostEqual(result["fixed_subscription_usd_per_calendar_hour"], 400 / 744, places=4)
        with self.conn:
            self.conn.execute("UPDATE accounting_snapshots SET source_signature='other' WHERE strict_full_c=82")
        self.assertIsNone(ops_metrics.summary(self.conn, now=datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc))["completion_rate"])

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

    def test_agent_delivery_ingestion_is_append_only_and_content_free(self):
        source = Path(self.temporary.name) / "events.db"
        import sqlite3
        with sqlite3.connect(source) as conn:
            conn.execute("CREATE TABLE events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,pane_id TEXT,source TEXT,sender TEXT,mailbox TEXT,bytes INTEGER,duration_ms INTEGER,attempts INTEGER)")
            conn.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)", [
                (1, 1792200000, "inbox.sent", "wN:pF", "inbox", "poolrad-codex", "C lane", 42, None, None),
                (2, 1792200030, "message.sent", "wN:pF", "send_text", "x@example.com", "C lane", 20, 150, 1),
                (3, 1792200040, "inbox.read", "wN:pF", "inbox", None, "C lane", None, None, None),
            ])
        first = ops_metrics._new_agent_message_events(self.conn, source)
        self.assertEqual(len(first), 2)
        self.assertEqual(first[0][5], "poolrad-codex")
        self.assertIsNone(first[1][5])
        self.assertEqual(first[1][7:10], (20, 150, 1))
        with self.conn:
            self.conn.executemany(
                "INSERT INTO agent_message_events"
                "(source_event_id,occurred_at,pane_id,kind,delivery_source,sender_alias,mailbox_alias,message_bytes,duration_ms,attempts,source_ref) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)", first
            )
        self.assertEqual(ops_metrics._new_agent_message_events(self.conn, source), [])
        result = ops_metrics.experiment_summary(
            self.conn, datetime.fromtimestamp(1792200100, timezone.utc)
        )
        self.assertEqual(result["messages_by_pane"][0]["inbox_deliveries"], 1)
        self.assertEqual(result["messages_by_pane"][0]["direct_sends"], 1)

    def test_trial_and_body_events_keep_authored_separate_from_reviewed_credit(self):
        start = "2026-10-17T02:00:00Z"
        end = "2026-10-17T03:00:00Z"
        ops_metrics.record_trial(
            self.conn, trial_id="sonnet-a", pane="wN:pT", agent_type="claude",
            provider="claude", model="sonnet", reasoning_effort="low",
            hypothesis="whole body in less time", started_at=start, ended_at=end,
            metered_usd=2.0, usage_source="provider bill", evidence="trial log",
        )
        ops_metrics.record_body(
            self.conn, function_id="U25+20CC", status="authored", pane="wN:pT",
            source_head="abcdef1234567", evidence="local review", trial_id="sonnet-a",
        )
        before = ops_metrics.experiment_summary(
            self.conn, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(before["authored_bodies"], 1)
        self.assertEqual(before["accepted_bodies"], 0)
        with self.assertRaisesRegex(ValueError, "named reviewer"):
            ops_metrics.record_body(
                self.conn, function_id="U25+20CC", status="accepted", pane="wN:pT",
                source_head="abcdef1234567", evidence="unchecked", trial_id="sonnet-a",
            )
        ops_metrics.record_body(
            self.conn, function_id="U25+20CC", status="accepted", pane="wN:pT",
            source_head="abcdef1234567", evidence="source completeness", trial_id="sonnet-a",
            reviewed_by="PM",
        )
        result = ops_metrics.experiment_summary(
            self.conn, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(result["accepted_bodies"], 1)
        self.assertEqual(result["trials"][0]["accepted_per_hour"], 1)
        self.assertEqual(result["trials"][0]["accepted_per_usd"], 0.5)
        self.assertIsNone(ops_metrics.summary(self.conn)["function_progress"])

    def test_acceptance_inherits_trial_only_from_matching_authored_head(self):
        ops_metrics.record_trial(
            self.conn, trial_id="opus-body", pane="wN:pV", agent_type="claude",
            provider="anthropic", model="Claude Opus 5.5", reasoning_effort="extended",
            hypothesis="complete two bodies", started_at="2026-10-17T02:00:00Z",
            ended_at="2026-10-17T03:00:00Z", evidence="trial log",
        )
        for function_id, head in (("U38+2D38", "abcdef1234567"),
                                  ("U38+2D88", "1234567abcdef")):
            ops_metrics.record_body(
                self.conn, function_id=function_id, status="authored", pane="wN:pV",
                source_head=head, evidence="trial source", trial_id="opus-body",
            )
        ops_metrics.record_body(
            self.conn, function_id="U38+2D38", status="accepted", pane="wN:p1",
            source_head="abcdef1234567", evidence="PM exact-head review", reviewed_by="PM",
        )
        ops_metrics.record_body(
            self.conn, function_id="U38+2D88", status="accepted", pane="wN:p1",
            source_head="deadbee123456", evidence="PM changed-head review", reviewed_by="PM",
        )
        links = dict(self.conn.execute(
            "SELECT function_id,trial_id FROM function_body_events WHERE status='accepted'"
        ))
        self.assertEqual(links, {"U38+2D38": "opus-body", "U38+2D88": None})
        result = ops_metrics.experiment_summary(
            self.conn, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(result["accepted_bodies"], 2)
        self.assertEqual(result["trials"][0]["accepted_bodies"], 1)

    def test_late_backfill_does_not_erase_newer_acceptance(self):
        head = "abcdef1234567"
        ops_metrics.record_trial(
            self.conn, trial_id="u16-body-trial", pane="w9:p5", agent_type="codex",
            provider="openai", model="GPT-6-Sol", reasoning_effort="high",
            hypothesis="complete U16 body", started_at="2026-10-17T04:00:00Z",
            ended_at="2026-10-17T05:00:00Z", evidence="dated source trial",
        )
        ops_metrics.record_body(
            self.conn, function_id="U16+0042", status="accepted", pane="wN:p1",
            source_head=head, evidence="PM exact-head acceptance", reviewed_by="PM",
            occurred_at="2026-10-17T04:30:00Z",
        )
        ops_metrics.record_body(
            self.conn, function_id="U16+0042", status="authored", pane="w9:p5",
            source_head=head, evidence="late authored-event import", trial_id="u16-body-trial",
            occurred_at="2026-10-17T04:20:00Z",
        )
        result = ops_metrics.experiment_summary(
            self.conn, datetime(2026, 10, 17, 4, 40, tzinfo=timezone.utc)
        )
        self.assertEqual(result["bodies"][0]["status"], "accepted")
        self.assertEqual(result["accepted_bodies"], 1)
        self.assertEqual(result["bodies"][0]["trial_id"], "u16-body-trial")
        self.assertEqual(result["trials"][0]["accepted_bodies"], 1)

    def test_model_comparison_merges_case_variants_without_rewriting_trials(self):
        for trial_id, model in (("first", "gpt-6-sol"),
                                ("second", "GPT-6-Sol")):
            ops_metrics.record_trial(
                self.conn, trial_id=trial_id, pane="wN:pF", agent_type="codex",
                provider="openai", model=model, reasoning_effort="high",
                hypothesis="compare complete bodies", started_at="2026-10-17T02:00:00Z",
                ended_at="2026-10-17T02:10:00Z", evidence="local trial",
            )
        result = ops_metrics.experiment_summary(
            self.conn, datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(len(result["efficiency_by_type_model"]), 1)
        group = result["efficiency_by_type_model"][0]
        self.assertEqual(group["model"], "GPT-6-Sol")
        self.assertEqual(group["completed_trials"], 2)
        self.assertEqual({row["model"] for row in result["trials"]},
                         {"gpt-6-sol", "GPT-6-Sol"})
