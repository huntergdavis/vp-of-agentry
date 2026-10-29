"""Optional integration with an installed Poolrad CLI; only synthetic save bytes.

Set POOLRAD_EDITOR_TEST_TOOL to the accepted edit_save.py to exercise its real
inspect/no-op code. Synthetic hashes must never unlock reference editing.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from server.character_editor import CopyRequest, EditorError, EditorStore


def synthetic_files():
    character = bytearray(285)
    character[0x10:0x16] = bytes([17, 12, 12, 17, 16, 15])
    character[0x98] = 1
    world = bytearray(13137)
    world[0x3208:0x3212] = bytes([1, 8]) + b'CHRDATA1'
    return {'CHRDATA1.SAV': bytes(character), 'CHRDATA1.ITM': bytes(63),
            'CHRDATA1.SPC': bytes(9), 'SAVGAMA.DAT': bytes(world)}


@unittest.skipUnless(os.environ.get('POOLRAD_EDITOR_TEST_TOOL'), 'Requires an explicit accepted Poolrad CLI path')
class RealCLIIntegration(unittest.TestCase):
    def test_four_file_noop_reexport_and_unmatched_profile_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            store = EditorStore(Path(temp), Path(os.environ['POOLRAD_EDITOR_TEST_TOOL']))
            files = synthetic_files()
            original_hashes = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}
            source = store.import_files(list(files.items()))
            self.assertEqual(original_hashes, source['expected_source_hashes'])
            self.assertFalse(any(p['eligible'] for c in source['characters'] for p in c['profiles']))
            self.assertIsNone(source['characters'][0]['reference_fighter_level'])
            request = dict(source_id=source['id'], copy_name='Synthetic round trip',
                           expected_source_hashes=original_hashes)
            with self.assertRaises(EditorError):
                store.copy(CopyRequest(**request, profiles=[dict(file='CHRDATA1.SAV',
                    validation_profile='reference_strength_17_to_16')]))
            for _ in range(2):
                result = store.copy(CopyRequest(**request))
                self.assertEqual(4, result['files_written'])
                self.assertEqual(4, result['byte_identical_files'])
                self.assertEqual('UNVERIFIED', result['game_validation'])
                self.assertIsNone(result['game_build_loaded'])
                self.assertEqual(1, result['receipt']['schema_version'])
                self.assertEqual(4, len(result['receipt']['files']))
                for row in result['receipt']['files']:
                    self.assertEqual(row['file'], row['source'])
                    self.assertEqual(original_hashes[row['file']], row['before_sha256'])
                    self.assertEqual(original_hashes[row['file']], row['after_sha256'])
                    self.assertEqual(len(files[row['file']]), row['size'])
                    self.assertEqual([], row['changed_offsets'])
                    self.assertEqual([], row['before_after_bytes'])
                    self.assertTrue(row['byte_identical'])
                    self.assertEqual('UNVERIFIED', row['game_validation'])
                    self.assertIsNone(row['game_build_loaded'])
                self.assertNotIn(temp, json.dumps(result))
                _, data = store.download(result['id'])
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for name, expected in files.items():
                        self.assertEqual(expected, archive.read(name))
                    self.assertNotIn(temp, archive.read('write-receipts.json').decode())
                    self.assertEqual(result['receipt'], json.loads(archive.read('write-receipts.json')))
                self.assertEqual(original_hashes, store.inspect(source['id'])['expected_source_hashes'])
                request['source_id'] = result['id']  # An exported copy can itself round-trip.


if __name__ == '__main__':
    unittest.main()
