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


if __name__ == "__main__":
    unittest.main()
