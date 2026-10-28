"""Private Telegram pairing and configurable direct desk delivery."""

import importlib
import importlib.machinery
import importlib.util
import sqlite3
import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

desk = importlib.import_module("server.app")
server = desk
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
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("VP_TELEGRAM_CHANNEL", None)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        uploads = root / "uploads"
        uploads.mkdir()
        for target, value in ((desk, {"DATA": root, "DB": root / "messages.sqlite3", "UPLOADS": uploads}),
                              (bridge, {"CONFIG": root / "telegram.json", "LOCK": root / "telegram.lock"})):
            for name, replacement in value.items():
                context = patch.object(target, name, replacement)
                context.start()
                self.addCleanup(context.stop)
        desk._initialize()
        self.transport = FakeTransport()
        for name, replacement in (("_flock", lambda: self.transport),
                                  ("_panes", lambda: [{"pane_id": "test:" + channel, "tab_label": server.CHANNEL_INDEX[channel]["match"], "agent": "codex"} for channel in ("vp", "cos")])):
            context = patch.object(desk, name, replacement)
            context.start()
            self.addCleanup(context.stop)
        direct = patch.object(desk, "_send_to_pane", return_value={
            "outcome": "ok", "message_id": "m-test", "route": "guarded"})
        self.direct = direct.start()
        self.addCleanup(direct.stop)
        self.bot = FakeBot()
        self.config = {"bot_token": "private", "pair_code": "pair-code", "chat_id": None,
                       "last_brief_id": None, "update_offset": None}

    def set_channel(self, channel):
        (desk.DATA / "telegram-routing.json").write_text(json.dumps({"channel": channel}))

    @staticmethod
    def update(ident, chat_id, **content):
        return {"update_id": ident, "message": {"chat": {"id": chat_id, "type": "private"}, **content}}

    def pair(self):
        bridge.process_update(self.update(1, 42, text="/pair pair-code"), self.config, self.bot)
        self.assertEqual(42, self.config["chat_id"])
        self.assertEqual(0o600, bridge.CONFIG.stat().st_mode & 0o777)

    def test_only_paired_chat_reaches_direct_transport_once(self):
        bridge.process_update(self.update(1, 99, text="/pair bad-code"), self.config, self.bot)
        self.assertIsNone(self.config["chat_id"])
        self.pair()
        bridge.process_update(self.update(2, 99, text="stranger"), self.config, self.bot)
        message = self.update(3, 42, text="Please check Poolrad")
        bridge.process_update(message, self.config, self.bot)
        bridge.process_update(message, self.config, self.bot)
        with sqlite3.connect(desk.DB) as conn:
            rows = conn.execute("SELECT body,external_id,channel FROM messages WHERE role='owner'").fetchall()
        self.assertEqual([("Please check Poolrad", "telegram:3", "cos")], rows)
        self.assertEqual(1, self.direct.call_count)
        self.assertEqual("test:cos", self.direct.call_args.args[0])
        self.assertIn("[VP web message #", self.direct.call_args.args[1])
        self.assertFalse(any(method == "inbox_send" for method, _ in self.transport.calls))
        with desk._db() as conn:
            row = conn.execute("SELECT delivery,transport_id FROM messages WHERE external_id='telegram:3'").fetchone()
        self.assertEqual(("ok", "m-test"), tuple(row))

    def test_photo_and_new_brief_flow_through_existing_desk(self):
        self.pair()
        bridge.process_update(self.update(2, 42, caption="See this", photo=[{"file_id": "photo1", "file_size": 5}]),
                              self.config, self.bot)
        with sqlite3.connect(desk.DB) as conn:
            attachment = conn.execute("SELECT path FROM attachments WHERE message_id IS NOT NULL").fetchone()[0]
        self.assertEqual(b"image", Path(attachment).read_bytes())
        self.assertEqual(1, self.direct.call_count)
        self.assertIn(attachment, self.direct.call_args.args[1])
        self.assertFalse(any(method == "inbox_send" for method, _ in self.transport.calls))

        image = bridge.CONFIG.parent / "diagram.png"
        image.write_bytes(b"diagram")
        with sqlite3.connect(desk.DB) as conn:
            conn.execute("INSERT INTO attachments(id,filename,mime,size,path) VALUES(?,?,?,?,?)",
                         ("diagram", "diagram.png", "image/png", 7, str(image)))
        brief = desk.post_brief(desk.BriefIn(channel="cos", body="Progress", attachment_ids=["diagram"]), "api")
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(brief["id"], self.config["last_brief_id"])
        self.assertTrue(any("Progress" in args.get("text", "") for method, args in self.bot.calls if method == "sendMessage"))
        self.assertEqual([(42, "diagram.png", "image/png")], self.bot.files)
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(1, len(self.bot.files))

    def test_cos_reply_forwarding_leaves_vp_desk_usable(self):
        self.pair()
        vp = desk.post_brief(desk.BriefIn(channel="vp", body="VP desk only"), "api")
        cos = desk.post_brief(desk.BriefIn(channel="cos", body="CoS reply"), "api")
        bridge.send_briefs(self.config, self.bot)
        text = "\n".join(p.get("text", "") for _, p in self.bot.calls)
        self.assertIn("CoS reply", text)
        self.assertNotIn("VP desk only", text)
        with desk._db() as conn:
            self.assertEqual("VP desk only", conn.execute("SELECT body FROM messages WHERE id=?", (vp["id"],)).fetchone()[0])
        status = json.loads((desk.DATA / "telegram-status.json").read_text())
        self.assertEqual(cos["id"], status["last_brief_id"])
        self.assertEqual("cos", status["channel"])

    def test_channel_setting_and_environment_override_route_both_directions(self):
        for config_channel, override, expected in [("vp", None, "vp"), ("vp", "cos", "cos")]:
            with self.subTest(channel=config_channel, override=override):
                self.set_channel(config_channel)
                self.config.update(chat_id=None)
                if override is None:
                    os.environ.pop("VP_TELEGRAM_CHANNEL", None)
                else:
                    os.environ["VP_TELEGRAM_CHANNEL"] = override
                self.pair()
                ident = 10 if override is None else 11
                bridge.process_update(self.update(ident, 42, text="Route check"), self.config, self.bot)
                self.assertEqual("test:" + expected, self.direct.call_args.args[0])
                brief = desk.post_brief(desk.BriefIn(channel=expected, body="Reply " + expected), "api")
                bridge.send_briefs(self.config, self.bot)
                self.assertEqual(brief["id"], self.config["last_brief_id"])
                self.assertIn("Reply " + expected, self.bot.calls[-1][1]["text"])

    def test_status_uses_selected_channel(self):
        self.pair()
        desk.post_message(desk.MessageIn(channel="vp", body="Unrelated VP message", external_id="telegram:99"), "api")
        bridge.process_update(self.update(3, 42, text="CoS question"), self.config, self.bot)
        bridge.process_update(self.update(4, 42, text="/status"), self.config, self.bot)
        with desk._db() as conn:
            ident = conn.execute("SELECT id FROM messages WHERE channel='cos' AND role='owner'").fetchone()[0]
        self.assertIn(f"#{ident}: ok", self.bot.calls[-1][1]["text"])
        self.assertIn(desk.CHANNEL_INDEX["cos"]["name"], self.bot.calls[-1][1]["text"])

    def test_switch_resets_old_cursor_and_partial_send_without_replaying_history(self):
        self.config.update(chat_id=42, last_brief_id=99999, outbound_message_id=99999, outbound_part=2)
        old = desk.post_brief(desk.BriefIn(channel="cos", body="Historical CoS reply"), "api")
        bridge._prepare_route(self.config)
        self.assertEqual(old["id"], self.config["last_brief_id"])
        self.assertNotIn("outbound_message_id", self.config)
        self.assertNotIn("outbound_part", self.config)
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual([], self.bot.calls)
        new = desk.post_brief(desk.BriefIn(channel="cos", body="New CoS reply"), "api")
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(new["id"], self.config["last_brief_id"])
        self.assertEqual(1, len(self.bot.calls))
        self.assertIn("New CoS reply", self.bot.calls[0][1]["text"])
        bridge._prepare_route(self.config)
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(1, len(self.bot.calls))

    def test_same_channel_keeps_partial_send_resume(self):
        self.set_channel("vp")
        self.config.update(chat_id=42, last_brief_id=0)
        brief = desk.post_brief(desk.BriefIn(channel="vp", body="A" * 5000), "api")
        self.config.update(outbound_message_id=brief["id"], outbound_part=1)
        bridge.send_briefs(self.config, self.bot)
        self.assertEqual(1, len(self.bot.calls))
        self.assertLess(len(self.bot.calls[0][1]["text"]), 2000)
        self.assertEqual(brief["id"], self.config["last_brief_id"])

    def test_replayed_update_after_switch_is_not_delivered_twice(self):
        self.set_channel("vp")
        self.pair()
        update = self.update(3, 42, text="Deliver once")
        bridge.process_update(update, self.config, self.bot)
        self.set_channel("cos")
        bridge.process_update(update, self.config, self.bot)
        self.assertEqual(1, self.direct.call_count)
        with desk._db() as conn:
            rows = conn.execute("SELECT channel FROM messages WHERE external_id='telegram:3'").fetchall()
        self.assertEqual(["vp"], [row[0] for row in rows])

    def test_unknown_channel_fails_before_sending(self):
        self.set_channel("missing-channel")
        with self.assertRaisesRegex(ValueError, "configured desk channel"):
            bridge.process_update(self.update(1, 42, text="/pair pair-code"), self.config, self.bot)
        self.assertEqual([], self.bot.calls)
        self.direct.assert_not_called()

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
