import hashlib
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.emulator_build import describe_emulator, pinned_binary
from server.gameplay import GameError, GameSession
from server.state_archive import archive_status


class EmulatorStatusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.binary = self.root / 'dosbox-x'
        self.binary.write_bytes(b'synthetic executable')
        self.binary.chmod(0o700)
        self.digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        env = patch.dict(os.environ, {'VP_DOSBOX_X': str(self.binary)}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def session(self):
        return GameSession(self.root / 'repo', self.root / 'data')

    def test_identity_requires_hash_not_filename_or_sidecar(self):
        (self.root / 'provenance.json').write_text(json.dumps({'kind': 'checkpoint'}))
        actual = describe_emulator(str(self.binary))
        self.assertEqual(actual, dict(kind='other', build_id=None, sha256=self.digest, release=None))
        with patch('server.emulator_build.PINNED_SHA256', self.digest):
            self.assertEqual(describe_emulator(str(self.binary))['kind'], 'checkpoint')
            self.binary.write_bytes(b'tampered executable!')
            self.assertEqual(describe_emulator(str(self.binary))['kind'], 'other')

    def test_missing_binary_identity_is_unknown(self):
        self.assertEqual(describe_emulator(str(self.root / 'missing')),
                         dict(kind='other', build_id=None, sha256=None, release=None))

    def test_stopped_identity_is_for_next_start(self):
        result = self.session().status()
        self.assertFalse(result['running'])
        self.assertEqual(result['emulator']['scope'], 'next_start')
        self.assertEqual(result['emulator']['sha256'], self.digest)
        self.assertEqual(result['state_archive'], dict(status='pending', verified_count=0, archived_at=None))

    def test_running_identity_is_frozen_and_unknown_launch_stays_unknown(self):
        session = self.session()
        session.tmux_session = 'synthetic'
        session._game_running = lambda: True
        session._launched_emulator = describe_emulator(str(self.binary))
        self.binary.write_bytes(b'next executable')
        self.assertEqual(session.status()['emulator']['sha256'], self.digest)
        self.assertEqual(session.status()['emulator']['scope'], 'running_session')
        session._launched_emulator = None
        self.assertIsNone(session.status()['emulator']['sha256'])
        session.tmux_session = None
        self.assertNotEqual(session.status()['emulator']['sha256'], self.digest)

    def test_stopping_clears_launch_identity(self):
        session = self.session()
        session._launched_emulator = describe_emulator(str(self.binary))
        session._stop_locked()
        self.assertIsNone(session._launched_emulator)

    def test_default_and_single_variable_rollback(self):
        del os.environ['VP_DOSBOX_X']
        self.assertEqual(self.session().dosbox_x, '/usr/bin/dosbox-x')
        self.assertEqual(self.session().play_build, 'original')
        os.environ['VP_DOSBOX_X'] = pinned_binary()
        self.assertEqual(self.session().dosbox_x, pinned_binary())
        os.environ['VP_DOSBOX_X'] = '/usr/bin/dosbox-x'
        self.assertEqual(self.session().dosbox_x, '/usr/bin/dosbox-x')
        self.assertEqual(self.session().play_build, 'original')
        os.environ['VP_PLAY_BUILD'] = 'replacement'
        self.assertEqual(self.session().dosbox_x, pinned_binary())

    def test_bare_override_hash_and_launch_ignore_retained_tmux_path(self):
        server_bin, tmux_bin = self.root / 'server-bin', self.root / 'tmux-bin'
        for directory, label in ((server_bin, 'server'), (tmux_bin, 'retained-tmux')):
            directory.mkdir()
            script = directory / 'dosbox-x'
            script.write_text("#!/bin/sh\nprintf '%s' " + label + '\n')
            script.chmod(0o700)
        selected = server_bin / 'dosbox-x'
        expected_hash = hashlib.sha256(selected.read_bytes()).hexdigest()
        for mode in ('original', 'replacement'):
            with self.subTest(mode=mode):
                os.environ.update(PATH=str(server_bin), VP_PLAY_BUILD=mode,
                                  VP_DOSBOX_X='dosbox-x', VP_REPLACEMENT_DOSBOX_X='dosbox-x')
                session = self.session()
                os.environ['PATH'] = str(tmux_bin)
                command = session._dosbox_command(self.root)
                executable = command[command.index('--chdir') + 2]
                self.assertEqual(executable, str(selected.resolve()))
                identity = describe_emulator(session.dosbox_x)
                self.assertEqual(identity['sha256'], expected_hash)
                launched = subprocess.run([executable], env={'PATH': str(tmux_bin)},
                                          check=True, capture_output=True, text=True)
                self.assertEqual(launched.stdout, 'server')
                session._launched_emulator = identity
                session.tmux_session = 'synthetic'
                session._game_running = lambda: True
                self.assertEqual(session.status()['emulator']['sha256'], expected_hash)

    def test_missing_bare_override_has_clear_configuration_error(self):
        os.environ.update(PATH=str(self.root / 'absent'), VP_DOSBOX_X='missing-dosbox-x')
        with self.assertRaisesRegex(GameError, 'server PATH'):
            self.session()


class ArchiveStatusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manifest = self.root / 'manifest.json'
        self.state = self.root / 'state.sav'
        self.state.write_bytes(b'synthetic state')
        self.data = dict(schema=1, created='2026-10-25T21:00:00+00:00', expected_count=1,
                         entries=[dict(path='state.sav', size=self.state.stat().st_size,
                                       sha256=hashlib.sha256(self.state.read_bytes()).hexdigest())])

    def write(self):
        self.manifest.write_text(json.dumps(self.data))

    def test_verified_count_requires_complete_matching_files(self):
        self.assertEqual(archive_status(self.manifest)['status'], 'pending')
        self.write()
        self.assertEqual(archive_status(self.manifest),
                         dict(status='verified', verified_count=1, archived_at=self.data['created']))
        self.state.write_bytes(b'Synthetic state')
        self.assertEqual(archive_status(self.manifest),
                         dict(status='unavailable', verified_count=0, archived_at=None))

    def test_missing_duplicate_and_wrong_count_never_claim_verified(self):
        for mutation in ('missing', 'duplicate', 'count'):
            with self.subTest(mutation=mutation):
                data = json.loads(json.dumps(self.data))
                if mutation == 'missing':
                    data['entries'][0]['path'] = 'absent.sav'
                elif mutation == 'duplicate':
                    data['entries'] *= 2
                    data['expected_count'] = 2
                else:
                    data['expected_count'] = 2
                self.manifest.write_text(json.dumps(data))
                self.assertEqual(archive_status(self.manifest)['verified_count'], 0)

    def test_manifest_errors_and_path_escape_are_unavailable(self):
        for payload in ('{', '[]', '{}'):
            self.manifest.write_text(payload)
            self.assertEqual(archive_status(self.manifest)['status'], 'unavailable')
        for path in ('../state.sav', str(self.state)):
            self.data['entries'][0]['path'] = path
            self.write()
            self.assertEqual(archive_status(self.manifest)['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
