"""Service setup in a temporary tree; cold start needs the companion DS checkout."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TelegramInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.desk = self.base / "desk"
        self.desk.mkdir()
        (self.desk / "data").mkdir()
        (self.desk / "data/telegram.json").write_text("{}")
        shutil.copy2(ROOT / "install-telegram-service.sh", self.desk)
        self.ds = self.base / "Dunking Sheep"
        self.ds.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.calls = self.base / "systemctl-calls"
        fake = self.bin / "systemctl"
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_SYSTEMCTL_LOG"\n')
        fake.chmod(0o700)
        self.env = dict(os.environ, DUNKING_SHEEP_DIR=str(self.ds),
                        XDG_CONFIG_HOME=str(self.base / "config"),
                        TEST_SYSTEMCTL_LOG=str(self.calls),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"])
        self.env.pop("PYTHONPATH", None)
        self.unit = self.base / "config/systemd/user/vp-telegram.service"

    def install(self):
        return subprocess.run(["bash", str(self.desk / "install-telegram-service.sh")],
                              env=self.env, capture_output=True, text=True)

    def test_unit_explicitly_names_shared_resolver_checkout(self):
        (self.ds / "dunk_telegram_routing.py").write_text('# resolver fixture\n')
        result = self.install()
        self.assertEqual(0, result.returncode, result.stderr)
        unit = self.unit.read_text()
        self.assertIn(f'Environment="DUNKING_SHEEP_DIR={self.ds}"', unit)
        self.assertIn(f'Environment="PYTHONPATH={self.ds}"', unit)
        self.assertIn(f"ExecStart={self.desk}/telegram-bridge run", unit)
        self.assertEqual(["--user daemon-reload", "--user enable --now vp-telegram.service",
                          "--user status vp-telegram.service --no-pager"],
                         self.calls.read_text().splitlines())

    def test_missing_resolver_preserves_unit_and_never_calls_systemctl(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('existing unit\n')
        result = self.install()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Install Dunking Sheep PR47 first", result.stderr)
        self.assertEqual('existing unit\n', self.unit.read_text())
        self.assertFalse(self.calls.exists())

    def cold_environment(self):
        ds = os.environ.get("DUNKING_SHEEP_DIR")
        self.assertTrue(ds and (Path(ds) / "dunk_telegram_routing.py").is_file(),
                        "Set DUNKING_SHEEP_DIR to the companion PR47 checkout")
        data = self.base / "cold-data"
        data.mkdir()
        (data / "telegram.json").write_text("{}")  # synthetic config, no secrets
        env = dict(os.environ, VP_DATA_DIR=str(data),
                   VP_CHANNELS_FILE=str(ROOT / "channels.example.json"))
        env.pop("PYTHONPATH", None)
        return env

    def test_cold_import_without_pythonpath_finds_the_selected_shared_module(self):
        env = self.cold_environment()
        code = ("import json, telegram_bridge as b, dunk_telegram_routing as r; "
                "print(json.dumps({'same': b.resolve_telegram_channel is r.resolve_telegram_channel, "
                "'path': r.__file__, 'channel': b._channel({})}))")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        value = json.loads(result.stdout)
        self.assertTrue(value["same"])
        self.assertEqual("cos", value["channel"])
        self.assertEqual(Path(env["DUNKING_SHEEP_DIR"]).resolve(),
                         Path(value["path"]).resolve().parent)

    def test_real_launcher_status_without_pythonpath_uses_only_fixture_data(self):
        result = subprocess.run([str(ROOT / "telegram-bridge"), "status"], cwd=ROOT,
                                env=self.cold_environment(), capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("channel=cos;", result.stdout)
        self.assertIn("paired=no;", result.stdout)


if __name__ == "__main__":
    unittest.main()
