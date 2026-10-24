"""Channel routing comes from a local file, with a generic clean-checkout default."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import app as server


class ChannelConfigTests(unittest.TestCase):
    def test_private_file_and_generic_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = [{"id": "vp", "name": "Example", "match": "example pane", "kind": "active"}]
            private = [{"id": "vp", "name": "Private", "match": "private pane", "kind": "active"}]
            (root / "channels.example.json").write_text(json.dumps(example))
            (root / "channels.json").write_text(json.dumps(private))
            with patch.object(server, "ROOT", root), patch.dict("os.environ", {}, clear=False):
                with patch.dict("os.environ", {"VP_CHANNELS_FILE": ""}):
                    self.assertEqual(server._load_channels(), private)
                    (root / "channels.json").unlink()
                    self.assertEqual(server._load_channels(), example)

    def test_explicit_missing_and_duplicate_ids_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "channels.json"
            with patch.dict("os.environ", {"VP_CHANNELS_FILE": str(path)}):
                with self.assertRaises(FileNotFoundError):
                    server._load_channels()
                item = {"id": "vp", "name": "Example", "match": "pane", "kind": "active"}
                path.write_text(json.dumps([item, item]))
                with self.assertRaisesRegex(ValueError, "duplicate channel id"):
                    server._load_channels()

    def test_pane_pin_must_be_a_pane_id_and_live_config_pins_cos(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "channels.json"
            item = {"id": "cos", "name": "Chief", "match": "chief-of-staff", "kind": "active"}
            with patch.dict("os.environ", {"VP_CHANNELS_FILE": str(path)}):
                path.write_text(json.dumps([{**item, "pane": "w9:pS"}]))
                self.assertEqual(server._load_channels()[0]["pane"], "w9:pS")
                path.write_text(json.dumps([{**item, "pane": "chief-of-staff"}]))
                with self.assertRaisesRegex(ValueError, "pane must be a herdr pane id"):
                    server._load_channels()
