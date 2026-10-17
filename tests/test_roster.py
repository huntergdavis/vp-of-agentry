"""The desk roster reflects live panes without losing configured chat IDs."""

import unittest

from server.roster import build_roster, discovered_id


class RosterTests(unittest.TestCase):
    def test_configured_and_new_panes_follow_live_status(self):
        configured = [{"id": "vp", "name": "VP", "match": "VP of Agentry", "kind": "active"},
                      {"id": "old", "name": "Old project", "match": "old", "kind": "active"}]
        panes = [{"pane_id": "w1:p1", "tab_label": "VP of Agentry", "workspace_label": "admin",
                  "agent": "codex", "agent_status": "working"},
                 {"pane_id": "w2:p3", "tab_label": "New Fable", "workspace_label": "poolrad",
                  "agent": "claude", "agent_status": "idle"},
                 {"pane_id": "w2:p4", "tab_label": "terminal", "workspace_label": "poolrad",
                  "agent_status": "unknown"}]
        rows = build_roster(configured, panes)
        self.assertEqual([(r["id"], r["activity_group"]) for r in rows],
                         [("vp", "active"), ("old", "standby"), (discovered_id("w2:p3"), "standby")])
        self.assertEqual(rows[-1]["workspace"], "poolrad")
        self.assertTrue(rows[-1]["can_message"])


if __name__ == "__main__":
    unittest.main()
