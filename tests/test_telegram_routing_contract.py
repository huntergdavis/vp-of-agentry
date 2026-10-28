"""Both real consumers must resolve one nonsecret fixture identically.

Requires the companion Dunking Sheep PR47 checkout (shared module + watchdog):
DUNKING_SHEEP_DIR=/path/to/dunkingsheep .venv/bin/python -m unittest \
    tests.test_telegram_bridge tests.test_telegram_routing_contract
No caller-supplied PYTHONPATH is needed: server.app registers that DS checkout.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_telegram_bridge import bridge, desk
import dunk_watchdog as watchdog


class SharedTelegramRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.routing = self.data / "telegram-routing.json"
        self.status = self.data / "telegram-status.json"
        (self.root / "channels.json").write_text(json.dumps([{"id": "cos"}, {"id": "vp"}]))
        # Deliberately unreadable as JSON: resolution must never consult it.
        self.credentials = self.data / "telegram.json"
        self.credentials.write_text("credential sentinel: DO NOT OPEN")
        for context in [patch.dict(os.environ), patch.object(desk, "DATA", self.data),
                        patch.object(desk, "ROOT", self.root)]:
            context.start()
            self.addCleanup(context.stop)
        os.environ.pop("VP_TELEGRAM_CHANNEL", None)
        os.environ.pop("VP_CHANNELS_FILE", None)
        original_open = Path.open
        credential_path = self.credentials

        def guarded_open(path, *args, **kwargs):
            if path == credential_path:
                raise AssertionError("routing reader opened bot credentials")
            return original_open(path, *args, **kwargs)

        guard = patch.object(Path, "open", guarded_open)
        guard.start()
        self.addCleanup(guard.stop)
        self.consumer = watchdog.DeskBriefChannel(self.status)

    def read_both(self):
        return bridge._channel({}), self.consumer.desk_channel

    def test_same_resolver_function_is_imported_by_both(self):
        self.assertIs(bridge.resolve_telegram_channel, watchdog.resolve_telegram_channel)

    def test_absent_routing_file_uses_same_default(self):
        self.assertFalse(self.routing.exists())
        self.assertEqual(("cos", "cos"), self.read_both())

    def test_empty_config_and_explicit_config_use_same_route(self):
        for value, expected in [({}, "cos"), ({"channel": "cos"}, "cos"), ({"channel": "vp"}, "vp")]:
            with self.subTest(config=value):
                self.routing.write_text(json.dumps(value))
                self.assertEqual((expected, expected), self.read_both())

    def test_environment_overrides_same_config_for_both(self):
        for config, environment in [("cos", "vp"), ("vp", "cos")]:
            with self.subTest(config=config, environment=environment):
                self.routing.write_text(json.dumps({"channel": config}))
                os.environ["VP_TELEGRAM_CHANNEL"] = environment
                self.assertEqual((environment, environment), self.read_both())

    def test_invalid_setting_is_refused_by_both(self):
        for config, environment in [({"channel": "unknown"}, None),
                                    ({"channel": "cos"}, "unknown"),
                                    ({"channel": "vp"}, ""),
                                    ({"channel": None}, None)]:
            with self.subTest(config=config, environment=environment):
                self.routing.write_text(json.dumps(config))
                os.environ.pop("VP_TELEGRAM_CHANNEL", None)
                if environment is not None:
                    os.environ["VP_TELEGRAM_CHANNEL"] = environment
                for reader in [lambda: bridge._channel({}), lambda: self.consumer.desk_channel]:
                    with self.assertRaises(ValueError):
                        reader()

    def test_wrong_but_valid_route_agrees_and_rejects_other_channel_status(self):
        self.routing.write_text(json.dumps({"channel": "vp"}))
        self.assertEqual(("vp", "vp"), self.read_both())
        self.status.write_text(json.dumps({"channel": "cos", "last_brief_id": 999999}))
        with self.assertRaisesRegex(ValueError, "channel"):
            self.consumer.confirmed_through()
        self.status.write_text(json.dumps({"channel": "vp", "last_brief_id": 42}))
        self.assertEqual(42, self.consumer.confirmed_through())
