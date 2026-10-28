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
                server._reconcile("vp")
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
