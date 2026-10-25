import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fleet_inventory as inventory


class InventoryTests(unittest.TestCase):
    def test_detects_harness_names_without_matching_prompt_text_or_services(self):
        self.assertEqual('claude', inventory.harness(['claude'], '/versions/2.1.7'))
        self.assertEqual('pi', inventory.harness(['node','/pkg/pi-coding-agent/dist/cli.js'], '/usr/bin/node'))
        self.assertIsNone(inventory.harness(['bash','-c','codex do private work'], '/usr/bin/bash'))
        self.assertIsNone(inventory.harness(['codex','app-server'], '/bin/codex'))

    def test_unrouted_and_nested_agents_stay_visible(self):
        processes={1:dict(pid=1,ppid=0,agent=None),
                   2:dict(pid=2,ppid=1,agent='pi',cwd='/work/routed'),
                   3:dict(pid=3,ppid=0,agent='codex',cwd='/work/unrouted'),
                   4:dict(pid=4,ppid=2,agent='claude',cwd='/work/helper'),
                   5:dict(pid=5,ppid=0,agent='pi',cwd='/work/unlisted-pane')}
        rows=inventory.unrouted(processes,{1:'%1',5:'%5'},{'%1'})
        self.assertEqual([3,4,5],[r['pid'] for r in rows])
        self.assertIn('No pane route',rows[0]['reason'])
        self.assertIn('independent pane route',rows[1]['reason'])
        self.assertIn('absent',rows[2]['reason'])

    def test_missing_or_ambiguous_session_age_is_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fd=root/'proc/123/fd';fd.mkdir(parents=True)
            home=root/'home';sessions=home/'.codex/sessions';sessions.mkdir(parents=True)
            self.assertIsNone(inventory.session_write(123,'codex',proc=root/'proc',home=home))
            one=sessions/'one.jsonl';one.write_text('not read by inventory');os.utime(one,(1000,1000))
            (fd/'1').symlink_to(one)
            self.assertEqual(1000,inventory.session_write(123,'codex',proc=root/'proc',home=home))
            two=sessions/'two.jsonl';two.write_text('not read either');(fd/'2').symlink_to(two)
            self.assertIsNone(inventory.session_write(123,'codex',proc=root/'proc',home=home))

    def test_inventory_failure_is_not_empty_success(self):
        with patch.object(inventory.subprocess,'run',side_effect=OSError('offline')):
            result=inventory.collect([])
        self.assertEqual('unavailable',result['state'])
        self.assertTrue(result['reason'])
