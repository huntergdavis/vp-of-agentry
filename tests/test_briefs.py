"""Agent briefs can carry private uploads without reusing owner attachments."""

import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

server = importlib.import_module("server.app")


class BriefAttachmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        database = patch.object(server, "DB", root / "messages.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        server._initialize()
        image = root / "loading.png"
        image.write_bytes(b"private image")
        with sqlite3.connect(server.DB) as conn:
            conn.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES(?,?,?,?,?)",
                         ("image", image.name, "image/png", image.stat().st_size, str(image)))

    def test_brief_links_uploaded_image_once(self):
        item = server.post_brief(server.BriefIn(
            channel="vp", body="DOS reference screen", attachment_ids=["image"]), "api")
        self.assertEqual("agent", item["role"])
        self.assertEqual("loading.png", item["attachments"][0]["filename"])
        with self.assertRaises(HTTPException) as error:
            server.post_brief(server.BriefIn(
                channel="vp", body="duplicate", attachment_ids=["image"]), "api")
        self.assertEqual(422, error.exception.status_code)

    def test_owner_token_cannot_post_agent_brief(self):
        with self.assertRaises(HTTPException) as error:
            server.post_brief(server.BriefIn(
                channel="vp", body="fake", attachment_ids=["image"]), "owner")
        self.assertEqual(403, error.exception.status_code)


class BriefAnswerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = patch.object(server, "DB", Path(temporary.name) / "messages.sqlite3")
        database.start()
        self.addCleanup(database.stop)
        server._initialize()
        with server._db() as conn:
            for channel, role in (("vp", "owner"), ("vp", "owner"), ("cos", "owner"), ("vp", "agent")):
                conn.execute("INSERT INTO messages(channel,role,body) VALUES(?,?,?)", (channel, role, "fixture"))

    def rows(self):
        with server._db() as conn:
            return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM messages")}

    def test_links_only_named_same_channel_owners_and_preserves_first_answer(self):
        first = server.post_brief(server.BriefIn(channel="vp", body="answer", answers=[1, 1, 3, 4, 999]), "api")
        rows = self.rows()
        self.assertEqual((rows[1]["answer_id"], rows[1]["answered_at"]), (first["id"], first["created_at"]))
        for identifier in (2, 3, 4, first["id"]):
            self.assertIsNone(rows[identifier]["answer_id"])
            self.assertIsNone(rows[identifier]["answered_at"])
        server.post_brief(server.BriefIn(channel="vp", body="retry", answers=[1]), "api")
        self.assertEqual(rows[1], self.rows()[1])

    def test_omitted_answers_and_schema_reinitialization_do_not_link_history(self):
        server.post_brief(server.BriefIn(channel="vp", body="status"), "api")
        server._initialize()
        self.assertTrue(all(r["answer_id"] is None and r["answered_at"] is None for r in self.rows().values()))

    def test_invalid_attachment_does_not_link_or_create_brief(self):
        before = self.rows()
        with self.assertRaises(HTTPException):
            server.post_brief(server.BriefIn(channel="vp", body="answer", answers=[1], attachment_ids=["missing"]), "api")
        self.assertEqual(before, self.rows())

    def test_answer_ids_are_positive_integers(self):
        from pydantic import ValidationError
        for value in (0, -1, 1.5, True, "1"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                server.BriefIn(channel="vp", body="answer", answers=[value])

    def test_old_schema_gets_nullable_columns_without_backfill(self):
        with server._db() as conn:
            conn.execute("ALTER TABLE messages DROP COLUMN answered_at")
            conn.execute("ALTER TABLE messages DROP COLUMN answer_id")
        server._initialize()
        self.assertTrue(all(r["answer_id"] is None and r["answered_at"] is None for r in self.rows().values()))


if __name__ == "__main__":
    unittest.main()
