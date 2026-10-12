"""Ambiguous transport outcomes never trigger an automatic duplicate send."""

import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

server = importlib.import_module("server.app")


class FakeTransport:
    def __init__(self):
        self.records = {}
        self.recent = []
        self.calls = []
        self.mailbox_keys = {}

    def call(self, command, **args):
        self.calls.append((command, args))
        if command == "get_message":
            record = self.records.get(args["message_id"])
            if record is None:
                raise RuntimeError(f"no message with id {args['message_id']!r}")
            return record
        if command == "list_messages":
            return {"queued": [record for record in self.records.values() if record["status"] == "queued"], "recent": self.recent}
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
        if command == "inbox_send":
            ident = f"i{len([c for c, _ in self.calls if c == 'inbox_send'])}"
            record = {"message_id": ident, "state": "queued", "pane_id": args["to"]}
            self.records[ident] = record
            return record
        if command == "inbox_count":
            return {"mailbox": self.mailbox_keys.get(args["mailbox"], "VP of Agentry"), "unread": 0}
        if command == "inbox_status":
            return self.records[args["message_id"]]
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

    def test_lost_queue_entry_is_uncertain_without_replay(self):
        message_id = self.add_message("lost")
        server._reconcile("vp")
        self.assertEqual(("uncertain", "lost"), self.row(message_id))
        server._reconcile("vp")
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))

    def test_web_send_is_stored_in_inbox_and_tracks_read_ack(self):
        item = server.post_message(server.MessageIn(channel="vp", body="hello"), "owner")
        self.assertEqual("inbox", item["delivery"])
        self.assertEqual("i1", item["transport_id"])
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))
        sent = next(args for command, args in self.transport.calls if command == "inbox_send")
        self.assertEqual("test:p1", sent["to"])
        self.assertIn(f"[VP web message #{item['id']};", sent["body"])
        self.transport.records["i1"]["notify"] = {"state": "queued", "reason": "input box contains a draft"}
        server._reconcile("vp")
        with sqlite3.connect(server.DB) as db:
            detail = db.execute("SELECT delivery_detail FROM messages WHERE id=?", (item["id"],)).fetchone()[0]
        self.assertIn("wakeup waiting", detail)
        self.transport.records["i1"]["state"] = "read"
        server._reconcile("vp")
        self.assertEqual(("read", "i1"), self.row(item["id"]))
        self.transport.records["i1"]["state"] = "acked"
        server._reconcile("vp")
        self.assertEqual(("acked", "i1"), self.row(item["id"]))

    def test_web_upload_is_copied_into_agent_inbox(self):
        path = Path(self.temporary.name) / "picture.png"
        path.write_bytes(b"test image bytes")
        with sqlite3.connect(server.DB) as db:
            db.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES(?,?,?,?,?)",
                       ("picture", "picture.png", "image/png", path.stat().st_size, str(path)))
        item = server.post_message(server.MessageIn(
            channel="vp", body="see the image", attachment_ids=["picture"]), "owner")
        self.assertEqual("inbox", item["delivery"])
        sent = next(args for command, args in self.transport.calls if command == "inbox_send")
        self.assertEqual([str(path)], sent["attach"])
        self.assertIn("picture.png", sent["body"])

    def test_generic_shared_mailbox_uses_exact_pane_send(self):
        self.transport.mailbox_keys["test:p1"] = "codex"
        item = server.post_message(server.MessageIn(channel="vp", body="review this"), "owner")
        self.assertEqual("queued", item["delivery"])
        self.assertFalse(any(command == "inbox_send" for command, _ in self.transport.calls))
        sent = next(args for command, args in self.transport.calls if command == "send_text")
        self.assertEqual("test:p1", sent["target"])
        self.assertTrue(sent["hold_while_typing"])

    def test_marker_prevents_duplicate_when_old_id_is_missing(self):
        message_id = self.add_message("lost")
        self.transport.recent = [{"message_id": "found", "status": "sent", "message": "sent",
                                  "text": f"hello [VP web message #{message_id}; reply through vpctl]"}]
        server._reconcile("vp")
        self.assertEqual(("sent", "found"), self.row(message_id))
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))

    def test_failed_transport_is_uncertain_without_replay(self):
        message_id = self.add_message("failed")
        with sqlite3.connect(server.DB) as db:
            db.execute("UPDATE messages SET delivery='failed' WHERE id=?", (message_id,))
        self.transport.records["failed"] = {"message_id": "failed", "status": "failed", "message": "pane busy"}
        server._reconcile("vp")
        self.assertEqual(("uncertain", "failed"), self.row(message_id))
        self.assertFalse(any(command == "send_text" for command, _ in self.transport.calls))

    def test_shared_timeout_never_replays(self):
        message_id = self.add_message("failed")
        with sqlite3.connect(server.DB) as db:
            db.execute("UPDATE messages SET delivery='failed' WHERE id=?", (message_id,))
        self.transport.records["failed"] = {"message_id": "failed", "status": "failed", "message": "herdr command timed out"}
        server._reconcile("vp")
        self.assertEqual(("uncertain", "failed"), self.row(message_id))
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

    def test_send_now_allows_message_behind_a_draft_hold(self):
        message_id = self.add_message("backlog")
        self.transport.records["backlog"] = {"message_id": "backlog", "status": "queued",
                                              "message": "queued for VP", "blocked_by": "input box contains a draft"}
        item = server.send_now(message_id, "owner")
        self.assertEqual("sent", item["delivery"])
        self.assertLess([c for c, _ in self.transport.calls].index("cancel_message"),
                        [c for c, _ in self.transport.calls].index("send_text"))

    def test_trailing_queue_reports_draft_blocker_to_web_chat(self):
        message_id = self.add_message("backlog")
        self.transport.records["backlog"] = {"message_id": "backlog", "status": "queued",
                                              "message": "queued for VP", "blocked_by": "input box contains a draft"}
        server._reconcile("vp")
        with sqlite3.connect(server.DB) as db:
            detail = db.execute("SELECT delivery_detail FROM messages WHERE id=?", (message_id,)).fetchone()[0]
        self.assertEqual("Waiting: input box contains a draft", detail)


if __name__ == "__main__":
    unittest.main()
