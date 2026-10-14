"""Herdr process state must not be presented as project health."""

import unittest
from unittest.mock import patch

from server import app as server
from server.app import _presence, channels


class PresenceTests(unittest.TestCase):
    def test_blocked_process_is_waiting_and_still_messageable(self):
        pane = {"pane_id": "test:p1", "tab_label": server.CHANNEL_INDEX["vp"]["match"], "agent": "codex", "agent_status": "blocked"}
        with patch("server.app._panes", return_value=[pane]):
            vp = next(row for row in channels("owner")["channels"] if row["id"] == "vp")
        self.assertEqual(vp["status"], "waiting")
        self.assertTrue(vp["can_message"])
        pane["agent_status"] = "working"
        with patch("server.app._panes", return_value=[pane]):
            vp = next(row for row in channels("owner")["channels"] if row["id"] == "vp")
        self.assertEqual(vp["status"], "working")
        self.assertTrue(vp["can_message"])


if __name__ == "__main__":
    unittest.main()
