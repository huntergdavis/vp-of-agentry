"""Private Telegram pairing and VP inbox delivery."""

import importlib
import importlib.machinery
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

desk = importlib.import_module("server.app")
bridge_path = Path(__file__).resolve().parents[1] / "telegram_bridge.py"
loader = importlib.machinery.SourceFileLoader("vp_telegram_bridge", str(bridge_path))
spec = importlib.util.spec_from_loader(loader.name, loader)
bridge = importlib.util.module_from_spec(spec)
loader.exec_module(bridge)


class FakeBot:
    def __init__(self):
        self.calls = []
        self.files = []

    def call(self, method, **payload):
        self.calls.append((method, payload))
        if method == "getFile":
            return {"file_path": "photo.jpg", "file_size": 5}
        return {"message_id": len(self.calls)}

    def download(self, file_id):
        return b"image"

    def send_file(self, chat_id, path, mime):
        self.files.append((chat_id, path.name, mime))


class FakeTransport:
    def __init__(self):
        self.calls = []

    def call(self, method, **kwargs):
        self.calls.append((method, kwargs))
        if method == "inbox_count":
            return {"mailbox": "VP of Agentry", "unread": 0}
        if method == "inbox_send":
            return {"message_id": "i1", "state": "queued"}
        if method == "inbox_status":
            return {"state": "queued"}
        raise AssertionError(method)


class TelegramBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        uploads = root / "uploads"
        uploads.mkdir()
        for target, value in ((desk, {"DB": root / "messages.sqlite3", "UPLOADS": uploads}),
                              (bridge, {"CONFIG": root / "telegram.json", "LOCK": root / "telegram.lock"})):
            for name, replacement in value.items():
                context = patch.object(target, name, replacement)
                context.start()
                self.addCleanup(context.stop)
        desk._initialize()
        self.transport = FakeTransport()
        for name, replacement in (("_flock", lambda: self.transport),
                                  ("_panes", lambda: [{"pane_id": "test:p1", "tab_label": "vp of agentry", "agent": "codex"}])):
            context = patch.object(desk, name, replacement)
            context.start()
            self.addCleanup(context.stop)
        self.bot = FakeBot()
        self.config = {"bot_token": "private", "pair_code": "pair-code", "chat_id": None,
                       "last_brief_id": None, "update_offset": None}

    @staticmethod
    def update(ident, chat_id, **content):
        return {"update_id": ident, "message": {"chat": {"id": chat_id, "type": "private"}, **content}}

    def pair(self):
        bridge.process_update(self.update(1, 42, text="/pair pair-code"), self.config, self.bot)
        self.assertEqual(42, self.config["chat_id"])
        self.assertEqual(0o600, bridge.CONFIG.stat().st_mode & 0o777)

    def test_only_paired_chat_reaches_durable_inbox_once(self):
        bridge.process_update(self.update(1, 99, text="/pair bad-code"), self.config, self.bot)
        self.assertIsNone(self.config["chat_id"])
        self.pair()
        bridge.process_update(self.update(2, 99, text="stranger"), self.config, self.bot)
        message = self.update(3, 42, text="Please check Poolrad")
        bridge.process_update(message, self.config, self.bot)
        bridge.process_update(message, self.config, self.bot)
        with sqlite3.connect(desk.DB) as conn:
            rows = conn.execute("SELECT body,external_id FROM messages WHERE role='owner'").fetchall()
        self.assertEqual([("Please check Poolrad", "telegram:3")], rows)
        sends = [args for method, args in self.transport.calls if method == "inbox_send"]
        self.assertEqual(1, len(sends))
        self.assertIn("[VP web message #", sends[0]["body"])

    def test_photo_and_new_brief_flow_through_existing_desk(self):
        self.pair()
        bridge.process_update(self.update(2, 42, caption="See this", photo=[{"file_id": "photo1", "file_size": 5}]),
                              self.config, self.bot)
        with sqlite3.connect(desk.DB) as conn:
            attachment = conn.execute("SELECT path FROM attachments WHERE message_id IS NOT NULL").fetchone()[0]
        self.assertEqual(b"image", Path(attachment).read_bytes())
        self.assertEqual(1, len([args for method, args in self.transport.calls if method == "inbox_send"]))

        image = bridge.CONFIG.parent / "diagram.png"
        image.write_bytes(b"diagram")
        with sqlite3.connect(desk.DB) as conn:
            conn.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES(?,?,?,?,?)",
                         ("diagram", "diagram.png", "image/png", 7, str(image)))
        brief = desk.post_brief(desk.BriefIn(channel="vp", body="Progress", attachment_ids=["diagram"]), "api")
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(brief["id"], self.config["last_brief_id"])
        self.assertTrue(any("Progress" in args.get("text", "") for method, args in self.bot.calls if method == "sendMessage"))
        self.assertEqual([(42, "diagram.png", "image/png")], self.bot.files)
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(1, len(self.bot.files))

    def test_long_brief_chunks_fit_telegram_limit(self):
        chunks = list(bridge._chunks("A" * 10000))
        self.assertEqual(10000, sum(map(len, chunks)))
        self.assertTrue(all(len(part) <= 3900 for part in chunks))

    def test_oversized_file_is_rejected_before_download(self):
        self.pair()
        bridge.process_update(self.update(2, 42, document={"file_id": "huge", "file_size": bridge.DOWNLOAD_LIMIT + 1}),
                              self.config, self.bot)
        self.assertFalse(any(method == "inbox_send" for method, _ in self.transport.calls))
        self.assertTrue(any("20 MB" in args.get("text", "") for method, args in self.bot.calls if method == "sendMessage"))

    def test_run_reaches_polling_with_private_lock(self):
        class StopPolling(Exception):
            pass

        class StartupBot:
            def call(self, method, **payload):
                if method == "getWebhookInfo":
                    return {"url": ""}
                if method == "getUpdates":
                    raise StopPolling
                raise AssertionError(method)

        bridge.save_config(self.config)
        with patch.object(bridge, "Telegram", return_value=StartupBot()):
            with self.assertRaises(StopPolling):
                bridge.run()
        self.assertEqual(0o600, bridge.LOCK.stat().st_mode & 0o777)


if __name__ == "__main__":
    unittest.main()
