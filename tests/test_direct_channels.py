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
