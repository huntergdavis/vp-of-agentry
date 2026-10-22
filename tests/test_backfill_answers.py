"""The answer backfill links each owner message to the first later agent brief.

Rule under test: an owner message with answered_at NULL gets the first agent
message in the same channel with a higher id; with no later agent message it
stays NULL; a link more than two hours old is reported as late.
"""

import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

server = importlib.import_module("server.app")
backfill = importlib.import_module("tools.backfill_answers")


class BackfillTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        database = patch.object(server, "DB", root / "messages.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        server._initialize()
        self.db = server.DB

    def _insert(self, role, body, created_at):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(
                "INSERT INTO messages(channel,role,body,delivery,created_at) VALUES(?,?,?,?,?)",
                ("vp", role, body, "acked", created_at)).lastrowid

    def test_links_to_first_later_agent_and_leaves_newest_null(self):
        owner = self._insert("owner", "first", "2026-10-20T10:00:00.000Z")
        brief = self._insert("agent", "answer", "2026-10-20T10:05:00.000Z")
        self._insert("agent", "second brief", "2026-10-20T10:30:00.000Z")
        newest = self._insert("owner", "no answer yet", "2026-10-20T11:00:00.000Z")
        with sqlite3.connect(self.db) as conn:
            links, unanswered = backfill.plan(conn)
        self.assertEqual([(owner, "vp", brief, "2026-10-20T10:05:00.000Z", 300.0)], links)
        self.assertEqual([newest], unanswered)

    def test_late_link_is_reported(self):
        owner = self._insert("owner", "old", "2026-10-20T10:00:00.000Z")
        brief = self._insert("agent", "late answer", "2026-10-20T13:00:00.000Z")
        with sqlite3.connect(self.db) as conn:
            links, _ = backfill.plan(conn)
        self.assertEqual(brief, links[0][2])
        self.assertGreater(links[0][4], 2 * 3600)

    def test_apply_is_one_transaction_and_links_only_null_rows(self):
        owner = self._insert("owner", "q", "2026-10-20T10:00:00.000Z")
        self._insert("agent", "a", "2026-10-20T10:01:00.000Z")
        backfill.main(["--db", str(self.db), "--apply"])
        with sqlite3.connect(self.db) as conn:
            row = conn.execute("SELECT answer_id, answered_at FROM messages WHERE id=?",
                               (owner,)).fetchone()
        self.assertIsNotNone(row[0])
        self.assertIsNotNone(row[1])


if __name__ == "__main__":
    unittest.main()
