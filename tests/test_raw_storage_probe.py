"""Storage fidelity is relative to writer input, not Markdown's rendered text."""
import unittest
from unittest.mock import patch

from tools.raw_storage_probe import EMPHASIS_TEXT, FIXTURE, FidelityError, StorageProbe, rendering_table


class RawStorageProbeTests(unittest.TestCase):
    def test_correct_emphasis_is_a_passing_control_despite_different_sql_and_dom_bytes(self):
        rows = rendering_table(FIXTURE, EMPHASIS_TEXT, [EMPHASIS_TEXT], ['bold'], 0)
        self.assertEqual(4, len(rows))
        self.assertTrue(all(row['status'] == 'PASS' for row in rows))
        self.assertNotEqual(rows[-1]['stored_utf8_hex'], rows[-1]['dom_utf8_hex'])

    def test_each_rendering_defect_fails_its_named_row(self):
        escaped = EMPHASIS_TEXT.replace('[', '\\[')
        missing_dollar = EMPHASIS_TEXT.replace('$901', '901')
        mutations = [
            ('literal_brackets', escaped, [escaped], ['bold'], 0),
            ('dollar_amount', missing_dollar, [missing_dollar], ['bold'], 0),
            ('paragraph_structure', EMPHASIS_TEXT, ['Cost $901, bold', 'and [brackets].'], ['bold'], 0),
            ('paragraph_structure', EMPHASIS_TEXT, [EMPHASIS_TEXT], ['bold'], 1),
            ('emphasis_control', EMPHASIS_TEXT, [EMPHASIS_TEXT], [], 0),
        ]
        for name, visible, paragraphs, strong, breaks in mutations:
            with self.subTest(defect=name, hard_breaks=breaks):
                rows = {r['assertion']: r for r in rendering_table(FIXTURE, visible, paragraphs, strong, breaks)}
                self.assertEqual([name], [key for key, row in rows.items() if row['status'] == 'FAIL'])

    def test_plain_and_composer_inputs_survive_every_raw_storage_boundary(self):
        wire = FIXTURE.replace('*', '\\*').replace('[', '\\[').replace(']', '\\]')
        with StorageProbe() as probe:
            probe.agent()
            probe.owner(FIXTURE)
            probe.owner(wire, 'owner_composer_wire')
            records = probe.finish()
            for name, record in records.items():
                self.assertEqual(record['input_utf8_hex'], record['api_utf8_hex'])
                boundaries = ['raw_after_write'] if name == 'agent_brief' else [
                    'raw_before_transport', 'raw_after_push', 'raw_after_pickup']
                for boundary in boundaries:
                    self.assertEqual(record['input_utf8_hex'], record[boundary]['body_hex'])
            self.assertEqual(wire, records['owner_composer_wire']['api_body'])
            self.assertEqual(0, records['agent_brief']['raw_after_write']['transport_attempt_at'])

    def test_extra_storage_escaping_is_rejected_before_it_can_hide_in_markdown(self):
        with StorageProbe() as probe:
            original = probe.server._prompt_for

            def corrupt(row, conn):
                conn.execute('UPDATE messages SET body=? WHERE id=?',
                             (row['body'].replace('[', '\\['), row['id']))
                return original(row, conn)

            with patch.object(probe.server, '_prompt_for', side_effect=corrupt):
                with self.assertRaisesRegex(FidelityError, 'UTF-8 bytes changed'):
                    probe.owner(FIXTURE)

    def test_api_body_corruption_is_detected_even_when_sql_is_intact(self):
        with StorageProbe() as probe:
            original = probe.server._message

            def corrupt(row, conn):
                item = original(row, conn)
                item['body'] = item['body'].replace('$901', '901')
                return item

            with patch.object(probe.server, '_message', side_effect=corrupt):
                with self.assertRaisesRegex(FidelityError, 'owner API after push'):
                    probe.owner(FIXTURE)


if __name__ == '__main__':
    unittest.main()
