"""A durable web row survives a lost in-memory queue entry."""

import importlib
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

server = importlib.import_module("server.app")


class FakeTransport:
    def __init__(self):
        self.records = {}
        self.recent = []
        self.calls = []

    def call(self, command, **args):
        self.calls.append((command, args))
        if command == "get_message":
            record = self.records.get(args["message_id"])
            if record is None:
                raise RuntimeError(f"no message with id {args['message_id']!r}")
            return record
        if command == "list_messages":
            return {"queued": [], "recent": self.recent}
        if command == "cancel_message":
            record = self.records[args["message_id"]]
            if record["status"] != "queued":
                raise RuntimeError("already sent")
            record["status"] = "cancelled"
            return record
        if command == "send_text":
            ident = f"test-{len([c for c, _ in self.calls if c == 'send_text'])}"
            status = "queued" if args["hold_while_typing"] else "sent"
            record = {"message_id": ident, "status": status, "queued": status == "queued",
                      "ok": True if status == "sent" else None, "message": status, "text": args["text"]}
            self.records[ident] = record
            return record
        raise AssertionError(command)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_patch = patch.object(server, "DB", Path(self.temporary.name) / "messages.sqlite3")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        server._initialize()
        self.transport = FakeTransport()
        self.client_patch = patch.object(server, "_flock", return_value=self.transport)
        self.panes_patch = patch.object(server, "_panes", return_value=[{"pane_id": "test:p1", "tab_label": "vp of agentry", "agent": "codex"}])
        self.client_patch.start(); self.panes_patch.start()
        self.addCleanup(self.client_patch.stop); self.addCleanup(self.panes_patch.stop)

    def add_message(self, ident):
        with sqlite3.connect(server.DB) as db:
            db.execute("INSERT INTO messages(channel,role,body,delivery,transport_id) VALUES('vp','owner','hello','queued',?)", (ident,))
            return db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def row(self, message_id):
        with sqlite3.connect(server.DB) as db:
            return db.execute("SELECT delivery,transport_id FROM messages WHERE id=?", (message_id,)).fetchone()

    def test_lost_queue_entry_is_requeued_then_marked_sent(self):
        message_id = self.add_message("lost")
        server._reconcile("vp")
        self.assertEqual(("queued", "test-1"), self.row(message_id))
        server._reconcile("vp")
        self.assertEqual(1, len([c for c, _ in self.transport.calls if c == "send_text"]))
        self.transport.records["test-1"]["status"] = "sent"
        server._reconcile("vp")
        self.assertEqual(("sent", "test-1"), self.row(message_id))

    def test_marker_prevents_duplicate_when_old_id_is_missing(self):
        message_id = self.add_message("lost")
        self.transport.recent = [{"message_id": "found", "status": "sent", "message": "sent",
                                  "text": f"hello [VP web message #{message_id}; reply through vpctl]"}]
        server._reconcile("vp")
        self.assertEqual(("sent", "found"), self.row(message_id))
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))

    def test_failed_transport_is_retried(self):
        message_id = self.add_message("failed")
        with sqlite3.connect(server.DB) as db:
            db.execute("UPDATE messages SET delivery='failed' WHERE id=?", (message_id,))
        self.transport.records["failed"] = {"message_id": "failed", "status": "failed", "message": "pane busy"}
        server._reconcile("vp")
        self.assertEqual(("queued", "test-1"), self.row(message_id))

    def test_shared_timeout_pauses_retries(self):
        message_id = self.add_message("failed")
        with sqlite3.connect(server.DB) as db:
            db.execute("UPDATE messages SET delivery='failed' WHERE id=?", (message_id,))
        self.transport.records["failed"] = {"message_id": "failed", "status": "failed", "message": "herdr command timed out"}
        self.transport.recent = [{"status": "failed", "message": "herdr command timed out", "finished_at": time.time()} for _ in range(3)]
        server._reconcile("vp")
        self.assertEqual(("failed", "failed"), self.row(message_id))
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))

    def test_send_now_cancels_held_copy_before_direct_send(self):
        message_id = self.add_message("held")
        self.transport.records["held"] = {"message_id": "held", "status": "queued", "message": "queued: someone is typing in VP"}
        item = server.send_now(message_id, "owner")
        self.assertEqual("sent", item["delivery"])
        commands = [command for command, _ in self.transport.calls]
        self.assertLess(commands.index("cancel_message"), commands.index("send_text"))
        direct = next(args for command, args in self.transport.calls if command == "send_text")
        self.assertFalse(direct["hold_while_typing"])

    def test_send_now_refuses_general_transport_backlog(self):
        message_id = self.add_message("backlog")
        self.transport.records["backlog"] = {"message_id": "backlog", "status": "queued", "message": "queued for VP"}
        with self.assertRaisesRegex(Exception, "queued for transport"):
            server.send_now(message_id, "owner")
        self.assertFalse(any(command == "cancel_message" for command, _ in self.transport.calls))


if __name__ == "__main__":
    unittest.main()
