"""An owner message is answered only by a brief that links it by id.

'acked' is transport, not an answer. The desk's pending count is the number of
owner messages with answer_id IS NULL, so publishing one brief that answers
two messages must drop it by exactly two.
"""

import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

server = importlib.import_module("server.app")


class AnswerLinkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        database = patch.object(server, "DB", root / "messages.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        server._initialize()
        with sqlite3.connect(server.DB) as conn:
            for _ in range(2):
                conn.execute("INSERT INTO messages(channel,role,body,delivery) VALUES(?,?,?,?)",
                             ("vp", "owner", "why is this still pending?", "acked"))

    def _unanswered(self):
        return server.messages("vp", "owner")["unanswered"]

    def _row(self, message_id):
        with sqlite3.connect(server.DB) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()

    def test_one_brief_answering_two_messages_links_both_and_drops_pending_by_two(self):
        self.assertEqual(2, self._unanswered())
        brief = server.post_brief(server.BriefIn(
            channel="vp", body="Both answered here.", answers=[1, 2]), "api")
        self.assertEqual("agent", brief["role"])
        for message_id in (1, 2):
            row = self._row(message_id)
            self.assertEqual(brief["id"], row["answer_id"])
            self.assertIsNotNone(row["answered_at"])
        self.assertEqual(0, self._unanswered())

    def test_acked_without_a_link_stays_unanswered(self):
        server.post_brief(server.BriefIn(channel="vp", body="Only the first.", answers=[1]), "api")
        self.assertEqual(1, self._unanswered())
        self.assertIsNone(self._row(2)["answer_id"])

    def test_link_refuses_a_message_from_another_channel_or_not_owner(self):
        brief = server.post_brief(server.BriefIn(channel="vp", body="hi"), "api")
        with self.assertRaises(HTTPException) as error:
            server.post_brief(server.BriefIn(
                channel="vp", body="not a link", answers=[brief["id"]]), "api")
        self.assertEqual(422, error.exception.status_code)
        with sqlite3.connect(server.DB) as conn:
            conn.execute("INSERT INTO messages(channel,role,body) VALUES(?,?,?)",
                         ("ops", "owner", "other channel"))
            other = conn.execute("SELECT id FROM messages WHERE channel='ops'").fetchone()[0]
        with self.assertRaises(HTTPException):
            server.post_brief(server.BriefIn(
                channel="vp", body="wrong channel", answers=[other]), "api")


if __name__ == "__main__":
    unittest.main()
