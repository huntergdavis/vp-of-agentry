"""The desk roster reflects live panes without losing configured chat IDs."""

import unittest

from server.roster import build_roster, discovered_id


class RosterTests(unittest.TestCase):
    def test_explicit_handoff_uses_current_vp_even_with_same_checkout(self):
        configured = [{"id": "vp", "name": "VP", "match": "vp of agentry",
                       "pane": "%15", "kind": "active"}]
        panes = [{"pane_id": pid, "tab_label": "pi", "cwd": "/work/vp-of-agentry",
                  "agent": "pi"} for pid in ("%1", "%15")]
        vp = build_roster(configured, panes)[0]
        self.assertEqual("%15", vp["pane_id"])
        self.assertTrue(vp["can_message"])

    def test_dead_explicit_target_does_not_fall_back_to_a_same_name_agent(self):
        configured = [{"id": "vp", "name": "VP", "match": "VP",
                       "pane": "%gone", "kind": "active"}]
        panes = [{"pane_id": "%other", "tab_label": "VP", "agent": "claude"}]
        vp = build_roster(configured, panes)[0]
        self.assertFalse(vp["online"])
        self.assertFalse(vp["can_message"])

    def test_configured_checkout_follows_renamed_agent_pane(self):
        configured = [{"id": "claude", "name": "Claude Fable", "match": "poolrad-decomp-claude-lane", "kind": "active"}]
        panes = [{"pane_id": "wR:p1", "tab_label": "renamed C lane", "workspace_label": "poolrad-decomp",
                  "cwd": "/home/hunter/workspace/poolrad-decomp-claude-lane", "agent": "claude", "agent_status": "working"}]
        rows = build_roster(configured, panes)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pane_id"], "wR:p1")
        self.assertEqual(rows[0]["activity_group"], "active")

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
