"""Direct chat receipts keep the daemon outcome and never enter inbox transport."""
import asyncio
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from starlette.requests import Request

server = importlib.import_module("server.app")


class DirectChannelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for key, value in (("DB", Path(self.temp.name) / "messages.sqlite3"),
                           ("_panes", lambda: [{"pane_id": "%2", "agent": "pi",
                                                "tab_label": server.CHANNEL_INDEX["vp"]["match"]}])):
            p = patch.object(server, key, value)
            p.start()
            self.addCleanup(p.stop)
        server._initialize()

    def send(self, **overrides):
        body = dict(pane="%2", channel="vp", text="Direct browser message")
        body.update(overrides)
        async def receive():
            return {"type": "http.request", "body": json.dumps(body).encode()}
        return asyncio.run(server.api_pane_send(Request({"type": "http"}, receive), "owner"))

    def test_receipts_attachments_and_history_preserve_every_outcome(self):
        for outcome in ("ok", "stored", "queued", "unconfirmed", "refused"):
            with self.subTest(outcome=outcome):
                receipt = dict(outcome=outcome, message_id="m-test", route="guarded", detail="daemon detail")
                with patch.object(server, "_send_to_pane", return_value=receipt) as send:
                    item = self.send()
                self.assertEqual(outcome, item["delivery"])
                self.assertEqual(outcome, item["outcome"])
                self.assertEqual("m-test", item["transport_id"])
                self.assertIn("Direct browser message", send.call_args.args[1])
                if outcome == "queued":
                    # Reconciliation now consults the durable daemon record for
                    # direct sends; a still-queued record on the bound pane with
                    # this row's creation marker keeps the queued outcome.
                    daemon = {"message_id": "m-test", "status": "queued", "outcome": "queued",
                              "pane_id": "%2",
                              "text": f"[VP web message #{item['id']};\nreply through vpctl] Direct browser message",
                              "message": "queued for %2, delivering once the input box is clear",
                              "created_at": 100.0, "finished_at": None}
                    flock = patch.object(server, "_flock")
                    started = flock.start(); started.new.return_value.call = lambda cmd, **a: daemon
                server._reconcile("vp")
                if outcome == "queued":
                    flock.stop()
                with server._db() as conn:
                    row = conn.execute("SELECT * FROM messages WHERE id=?", (item["id"],)).fetchone()
                    self.assertEqual(outcome, server._message(row, conn)["outcome"])
                    self.assertEqual(outcome, row["delivery"])
        path = Path(self.temp.name) / "test.txt"
        path.write_text("attachment")
        with server._db() as conn:
            conn.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES('a','test.txt','text/plain',10,?)", (str(path),))
        with patch.object(server, "_send_to_pane", return_value=receipt) as send:
            item = self.send(text="", attachment_ids=["a"])
        self.assertIn(str(path), send.call_args.args[1])
        self.assertEqual("a", item["attachments"][0]["id"])

    def test_compatibility_endpoint_uses_direct_transport_once(self):
        data = server.MessageIn(channel="vp", body="compatibility client", external_id="retry-1")
        with patch.object(server, "_send_to_pane", return_value={
            "outcome": "stored", "push_id": "p-test", "route": "owner_push"}) as send:
            first = server.post_message(data, "api")
            second = server.post_message(data, "api")
        self.assertEqual("stored", first["delivery"])
        self.assertEqual("p-test", first["transport_id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, send.call_count)

    def test_changed_target_never_sends(self):
        with patch.object(server, "_send_to_pane") as send:
            with self.assertRaises(server.HTTPException) as caught:
                self.send(pane="%15")
        self.assertEqual(409, caught.exception.status_code)
        send.assert_not_called()

    def test_timeout_is_saved_without_replay(self):
        with patch.object(server, "_send_to_pane", side_effect=TimeoutError("timeout")) as send:
            item = self.send()
            server._reconcile("vp")
        self.assertEqual("uncertain", item["delivery"])
        self.assertIsNone(item["outcome"])
        self.assertEqual(1, send.call_count)

    def pushed(self):
        with patch.object(server, "_send_to_pane", return_value={
                "outcome": "stored", "push_id": 7, "pane": "%2", "route": "owner_push"}), \
                patch.object(server.time, "time", return_value=100):
            return self.send(text="Cost $901, **bold** and [brackets].")

    def test_pickup_receipt_records_actual_latency_and_preserves_body_and_original_outcome(self):
        item = self.pushed()
        receipt = dict(id=7, pane_id="%2", created_at=100.5, taken_at=102.25)
        with patch.object(server, "_flock") as flock, patch.object(server.time, "time", return_value=109):
            flock.return_value.call.return_value = {"receipts": [receipt]}
            response = server.messages("vp", "owner")
            flock.return_value.call.assert_called_once_with("owner_receipts", push_ids=[7])
        delivered = response["items"][0]
        self.assertEqual("delivered", delivered["delivery"])
        self.assertEqual("stored", delivered["outcome"])
        self.assertEqual(102.25, delivered["delivered_at"])
        self.assertEqual(2.25, delivered["delivery_latency_s"])
        self.assertEqual(receipt, delivered["transport"]["pickup_receipt"])
        self.assertEqual(item["body"].encode(), delivered["body"].encode())
        self.assertEqual(item["id"], response["last_delivery"]["id"])
        # A later browser poll cannot inflate the recorded transport duration.
        with patch.object(server, "_flock") as flock:
            self.assertEqual(2.25, server.messages("vp", "owner")["last_delivery"]["delivery_latency_s"])
            flock.assert_not_called()

    def test_unproven_pickup_never_becomes_delivered(self):
        valid = dict(id=7, pane_id="%2", created_at=100.5, taken_at=102.25)
        responses = [{"receipts": []}, {}, {"receipts": [valid, valid]}]
        for changes in ({"id": 8}, {"id": "7"}, {"pane_id": "%9"}, {"taken_at": None},
                        {"taken_at": "102.25"}, {"taken_at": True}, {"taken_at": float("nan")},
                        {"created_at": 0}, {"taken_at": 200}):
            responses.append({"receipts": [{**valid, **changes}]})
        for response in responses:
            with self.subTest(response=response):
                with server._db() as conn:
                    conn.execute("DELETE FROM messages")
                self.pushed()
                with patch.object(server, "_flock") as flock, patch.object(server.time, "time", return_value=109):
                    flock.return_value.call.return_value = response
                    result = server.messages("vp", "owner")
                self.assertEqual("stored", result["items"][0]["delivery"])
                self.assertIsNone(result["items"][0]["delivered_at"])
                self.assertIsNone(result["last_delivery"])
        with patch.object(server, "_flock", side_effect=RuntimeError("older daemon")):
            self.assertEqual("stored", server.messages("vp", "owner")["items"][0]["delivery"])

    def test_legacy_zero_attempt_preserves_confirmed_pickup_without_duration(self):
        original = self.pushed()
        with server._db() as conn:
            conn.execute("UPDATE messages SET transport_attempt_at=0 WHERE id=?", (original["id"],))
        receipt = dict(id=7, pane_id="%2", created_at=100.5, taken_at=102.25)
        with patch.object(server, "_flock") as flock, patch.object(server.time, "time", return_value=109):
            flock.return_value.call.return_value = {"receipts": [receipt]}
            response = server.messages("vp", "owner")
        item = response["items"][0]
        self.assertEqual("delivered", item["delivery"])
        self.assertEqual(102.25, item["delivered_at"])
        self.assertIsNone(item["delivery_latency_s"])
        self.assertIn("send timestamp unavailable", item["delivery_detail"])
        self.assertEqual(receipt, item["transport"]["pickup_receipt"])
        self.assertEqual(original["body"], item["body"])
        self.assertEqual("stored", item["outcome"])
        self.assertEqual(original["id"], response["last_delivery"]["id"])
        self.assertIsNone(response["last_delivery"]["delivery_latency_s"])
        with patch.object(server, "_flock") as flock:
            self.assertIsNone(server.messages("vp", "owner")["last_delivery"]["delivery_latency_s"])
            flock.assert_not_called()

    def test_zero_attempt_still_requires_matched_receipt_and_saved_push_identity(self):
        valid = dict(id=7, pane_id="%2", created_at=100.5, taken_at=102.25)
        cases = [({}, []), ({}, [valid, valid]), ({}, [{**valid, "pane_id": "%9"}]),
                 ({}, [{**valid, "id": 8}]), ({}, [{**valid, "taken_at": None}]),
                 ({}, [{**valid, "taken_at": 200}]), ({}, [{**valid, "created_at": 0}]),
                 ({}, [{**valid, "taken_at": True}]), ({"transport_id": "8"}, [valid]),
                 ({"transport_attempt_at": -1}, [valid]),
                 ({"transport_attempt_at": "invalid"}, [valid]),
                 ({"transport_attempt_at": float("inf")}, [valid]),
                 ({"role": "agent"}, [valid]),
                 ({"direct_transport": json.dumps(dict(route="guarded", push_id=7, pane="%2"))}, [valid])]
        for changes, receipts in cases:
            with self.subTest(changes=changes, receipts=receipts):
                with server._db() as conn:
                    conn.execute("DELETE FROM messages")
                self.pushed()
                with server._db() as conn:
                    conn.execute("UPDATE messages SET transport_attempt_at=0")
                    for key, value in changes.items():
                        conn.execute(f"UPDATE messages SET {key}=?", (value,))
                with patch.object(server, "_flock") as flock, patch.object(server.time, "time", return_value=109):
                    flock.return_value.call.return_value = {"receipts": receipts}
                    response = server.messages("vp", "owner")
                self.assertEqual("stored", response["items"][0]["delivery"])
                self.assertIsNone(response["items"][0]["delivered_at"])
                self.assertIsNone(response["last_delivery"])

    def test_clock_step_preserves_pickup_without_claiming_elapsed_time(self):
        self.pushed()
        with patch.object(server, "_flock") as flock, patch.object(server.time, "time", return_value=104):
            flock.return_value.call.return_value = {"receipts": [
                dict(id=7, pane_id="%2", created_at=100.5, taken_at=99)]}
            item = server.messages("vp", "owner")["items"][0]
        self.assertEqual("delivered", item["delivery"])
        self.assertEqual(99, item["delivered_at"])
        self.assertIsNone(item["delivery_latency_s"])
        self.assertIn("wall clock moved", item["delivery_detail"])

    def test_last_delivery_is_channel_scoped_and_independent_of_history_window(self):
        self.pushed()
        with server._db() as conn:
            conn.execute("UPDATE messages SET delivery='delivered',delivered_at=102,delivery_latency_s=2")
            delivered_id = conn.execute("SELECT id FROM messages").fetchone()[0]
            conn.execute("INSERT INTO messages(channel,role,body) VALUES('vp','agent','Later reply')")
            conn.execute("INSERT INTO messages(channel,role,body,delivery,delivered_at,delivery_latency_s) "
                         "VALUES('cos','owner','Other channel','delivered',110,3)")
        with patch.object(server, "_flock") as flock:
            response = server.messages("vp", "owner", limit=1)
            flock.assert_not_called()
        self.assertEqual("Later reply", response["items"][0]["body"])
        self.assertEqual(delivered_id, response["last_delivery"]["id"])
        self.assertEqual(2, response["last_delivery"]["delivery_latency_s"])


class DirectReconcileTests(unittest.TestCase):
    """t362: a queued guarded direct send reconciles against the durable
    daemon record without replaying an ambiguous attempt, and only across an
    identity bound at send time."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for key, value in (("DB", Path(self.temp.name) / "messages.sqlite3"),
                           ("_panes", lambda: [{"pane_id": "%2", "agent": "pi",
                                                "tab_label": server.CHANNEL_INDEX["vp"]["match"]}])):
            p = patch.object(server, key, value)
            p.start()
            self.addCleanup(p.stop)
        server._initialize()

    def send(self, **overrides):
        body = dict(pane="%2", channel="vp", text="Direct browser message")
        body.update(overrides)
        async def receive():
            return {"type": "http.request", "body": json.dumps(body).encode()}
        return asyncio.run(server.api_pane_send(Request({"type": "http"}, receive), "owner"))

    def post(self, receipt):
        with patch.object(server, "_send_to_pane", return_value=receipt):
            return self.send()

    def daemon(self, record=None, error=None):
        calls = []
        client = self
        client.calls, client.error = calls, error
        client.durable = record
        class _Client:
            calls = client.calls
            def call(self, command, **args):
                calls.append((command, args))
                if command != "get_message":
                    raise AssertionError("unexpected " + command)
                if client.error is not None:
                    raise client.error
                if client.durable is None:
                    raise RuntimeError(f"no message with id {args['message_id']!r}")
                return client.durable
            def __getattr__(self, name):
                raise AssertionError("daemon method outside reconciliation")
        return _Client()

    @staticmethod
    def durable_record(**overrides):
        base = {"message_id": "m8365", "status": "sent", "outcome": "ok",
                "pane_id": "%2",
                "text": "[VP web message #1;\nreply through vpctl] Direct browser message",
                "message": "box cleared", "created_at": 100.0, "finished_at": 102.5}
        base.update(overrides)
        return base

    def row(self):
        with server._db() as conn:
            return conn.execute("SELECT * FROM messages").fetchone()

    def test_queued_direct_send_reconciles_to_sent_without_resend(self):
        sent = self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                              detail="held by the typing guard", pane="%2"))
        client = self.daemon(record=self.durable_record())
        with patch.object(server, "_flock", return_value=client):
            server._reconcile("vp")
        self.assertEqual([("get_message", {"message_id": "m8365"})],
                         [(c, a) for c, a in client.calls])  # reads only; never sends
        row = self.row()
        self.assertEqual("sent", row["delivery"])
        self.assertEqual("box cleared", row["delivery_detail"])
        self.assertEqual(102.5, row["delivered_at"])
        self.assertIsNone(row["delivery_latency_s"])  # no invented elapsed time
        self.assertEqual("m8365", row["transport_id"])  # identity preserved

    def test_still_queued_record_keeps_the_queued_state_with_daemon_detail(self):
        self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                       detail="held by the typing guard", pane="%2"))
        client = self.daemon(record=self.durable_record(status="queued", finished_at=None))
        with patch.object(server, "_flock", return_value=client):
            server._reconcile("vp")
        row = self.row()
        self.assertEqual("queued", row["delivery"])
        self.assertNotIn("would not", row["delivery_detail"])  # daemon's own prose

    def test_identity_mismatch_leaves_the_row_alone(self):
        self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                       detail="held by the typing guard", pane="%2"))
        cases = [
            self.durable_record(pane_id="%9"),                                # pane differs
            self.durable_record(text="unrelated text without the marker"),    # creation marker differs
        ]
        for record in cases:
            with self.subTest(pane=record.get("pane_id")):
                client = self.daemon(record=record)
                with patch.object(server, "_flock", return_value=client):
                    server._reconcile("vp")
                row = self.row()
                self.assertEqual("queued", row["delivery"])
                self.assertEqual("held by the typing guard", row["delivery_detail"])

    def test_unknown_state_and_outage_preserve_the_last_known_outcome(self):
        self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                       detail="held by the typing guard", pane="%2"))
        with self.subTest(state="failed"):
            client = self.daemon(record=self.durable_record(status="failed"))
            with patch.object(server, "_flock", return_value=client):
                server._reconcile("vp")
            self.assertEqual("queued", self.row()["delivery"])
        with self.subTest(state="daemon outage"):
            client = self.daemon(record=self.durable_record(), error=RuntimeError("daemon down"))
            with patch.object(server, "_flock", return_value=client):
                server._reconcile("vp")
            self.assertEqual("queued", self.row()["delivery"])

    def test_sent_record_resolves_an_uncertain_row(self):
        # t434 P1: a lost record marks the row uncertain; a later terminal
        # record with the row's full identity resolves the uncertainty to
        # sent - without any دوم replay.
        sent = self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                              detail="held by the typing guard", pane="%2"))
        client = self.daemon(record=None, error=RuntimeError("no message with id 'm8365'"))
        with patch.object(server, "_flock", return_value=client):
            server._reconcile("vp")
        self.assertEqual("uncertain", self.row()["delivery"])
        client = self.daemon(record=self.durable_record())
        with patch.object(server, "_flock", return_value=client):
            server._reconcile("vp")
        row = self.row()
        self.assertEqual("sent", row["delivery"])
        self.assertEqual(102.5, row["delivered_at"])
        self.assertIn("get_message", [c for c, _ in client.calls])
        self.assertNotIn("send_text", [c for c, _ in client.calls])

    def test_non_object_direct_receipt_is_rejected_per_row(self):
        # t434 P2: a corrupt stored receipt (list) is rejected on its own row;
        # unrelated legacy rows on the same channel still reconcile, and a
        # healthy guarded row later in the list still reaches the daemon.
        with patch.object(server, "_send_to_pane", side_effect=[
                dict(outcome="queued", message_id="m9001", route="guarded",
                     detail="held by the typing guard", pane="%2"),
                dict(outcome="queued", message_id="m9002", route="guarded",
                     detail="held by the typing guard", pane="%2")]):
            self.post(dict(outcome="queued", message_id="m9001", route="guarded",
                           detail="held by the typing guard", pane="%2"))
            self.post(dict(outcome="queued", message_id="m9002", route="guarded",
                           detail="held by the typing guard", pane="%2"))
        legacy_id = None
        with server._db() as conn:
            conn.execute("UPDATE messages SET direct_transport='[]' WHERE transport_id='m9001'")
            legacy_id = conn.execute(
                "INSERT INTO messages(channel,role,body,delivery,transport_id) "
                "VALUES('vp','owner','legacy text','queued','lost1')").fetchone()
            legacy_id = legacy_id if isinstance(legacy_id, int) else conn.execute(
                "SELECT last_insert_rowid()").fetchone()[0]
        # direct row gets a sent record; legacy row is missing from the daemon
        with server._db() as conn:
            row_ids = dict(conn.execute(
                "SELECT transport_id, id FROM messages WHERE transport_id IS NOT NULL").fetchall())
        row_ids["lost1"] = legacy_id
        calls = []
        class _Client:
            def call(self, command, **args):
                calls.append((command, args))
                if command == "list_messages":
                    return {"queued": [], "recent": []}
                assert command == "get_message", command
                if args["message_id"] == "lost1":
                    return {"message_id": "lost1", "status": "sent", "pane_id": "%2",
                            "text": "legacy text",
                            "message": "submitted", "created_at": 1.0,
                            "finished_at": 103.0}
                marker_id = row_ids[args["message_id"]]
                return {"message_id": args["message_id"], "status": "sent", "pane_id": "%2",
                        "text": "[VP web message #%d;\nreply through vpctl] Direct browser message" % marker_id,
                        "message": "submitted", "created_at": 100.0,
                        "finished_at": 101.0}
        with patch.object(server, "_flock", return_value=_Client()):
            server._reconcile("vp")
        with server._db() as conn:
            corrupt = conn.execute("SELECT delivery FROM messages WHERE transport_id='m9001'").fetchone()
            healthy = conn.execute("SELECT delivery FROM messages WHERE transport_id='m9002'").fetchone()
            legacy = conn.execute("SELECT delivery FROM messages WHERE id=?", (legacy_id,)).fetchone()
        self.assertEqual("queued", corrupt[0])  # corrupt receipt: rejected per row
        self.assertEqual("sent", healthy[0])    # healthy guarded row still reconciled
        self.assertEqual("sent", legacy[0])  # legacy row reconciled on its own path
        # healthy guarded row first, then the legacy pass (list_messages) and
        # the legacy row's own get_message - in that order, never a resend.
        self.assertEqual(["get_message", "list_messages", "get_message"],
                         [c for c, _ in calls])

    def test_malformed_timestamps_stay_absent_with_sent_status(self):
        self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                       detail="held by the typing guard", pane="%2"))
        for finished in (-1, float("inf")):
            with self.subTest(finished=finished):
                with server._db() as conn:
                    conn.execute("UPDATE messages SET delivery='queued',delivered_at=NULL")
                client = self.daemon(record=self.durable_record(finished_at=finished))
                with patch.object(server, "_flock", return_value=client):
                    server._reconcile("vp")
                row = self.row()
                self.assertEqual("sent", row["delivery"])
                self.assertIsNone(row["delivered_at"])
                self.assertIsNone(row["delivery_latency_s"])

    def test_vanished_record_becomes_uncertain_and_is_never_resent(self):
        self.post(dict(outcome="queued", message_id="m8365", route="guarded",
                       detail="held by the typing guard", pane="%2"))
        client = self.daemon(record=None, error=RuntimeError("no message with id 'm8365'"))
        with patch.object(server, "_flock", return_value=client), \
             patch.object(server, "_send_to_pane", side_effect=AssertionError("resend")):
            server._reconcile("vp")
        row = self.row()
        self.assertEqual("uncertain", row["delivery"])
        self.assertIn("unavailable", row["delivery_detail"])
