"""Programmatic save states and code-word detection for the Play desk.

The tests use a synthetic DOSBox slot file and synthetic rune frames, so no
private game media, emulator, or owner credentials are required. They exercise
the save/load round trip, tagged listing, endpoint wiring, and the ported
recognition primitives.
"""

import hashlib
import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import codeword
from server.gameplay import GameError, GameSession

server = importlib.import_module('server.app')


# --- Recognition primitives -------------------------------------------------

def _frame(width, height, shapes):
    rgb = bytearray(width * height * 3)
    for (x, y, w, h) in shapes:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                i = (yy * width + xx) * 3
                rgb[i], rgb[i + 1], rgb[i + 2] = 220, 10, 10
    return bytes(rgb)


def _mask(pixels, width, height):
    return bytearray(pixels)


def _template_set(esp_shape, det_shape):
    templates = []
    for ring, shape in (('esp', esp_shape), ('det', det_shape)):
        for number in range(1, 37):
            if shape and number == (7 if ring == 'esp' else 9):
                width, height = shape
                templates.append({'ring': ring, 'number': number,
                                  'normalized': codeword.normalize({'width': width, 'height': height,
                                                                    'pixels': bytearray([1] * (width * height))})})
            else:
                templates.append({'ring': ring, 'number': number, 'normalized': bytearray(32 * 32)})
    return templates


# Glyph 10x10 square (Espruar #7) and 6x14 bar (Dethek #9), plus a
# dash / two-dots path starting on a dash (path id 1) at y=110.
GLYPHS = [(40, 20, 10, 10), (40, 60, 6, 14)]
PATH = [(80, 109, 10, 3), (100, 108, 3, 4), (115, 108, 3, 4),
        (135, 109, 10, 3), (155, 108, 3, 4), (170, 108, 3, 4)]


class RecognitionTests(unittest.TestCase):
    def test_wheel_word_matches_reference_table(self):
        self.assertEqual('BEWARE', codeword.wheel_word(1, 1, 0))
        self.assertEqual('NOTNOW', codeword.wheel_word(5, 9, 0))
        self.assertEqual('IXYVSI', codeword.wheel_word(21, 36, 2))
        self.assertIsNone(codeword.wheel_word(0, 1, 0))
        self.assertIsNone(codeword.wheel_word(1, 1, 3))

    def test_confident_recognition_types_a_word(self):
        width, height = 320, 220
        rgb = _frame(width, height, GLYPHS + PATH)
        mask = codeword.bitmap_rgb(rgb, width, height, 'rune')
        result = codeword.recognize_wheel(mask, _template_set((10, 10), (6, 14)))
        self.assertTrue(result['confident'], result)
        self.assertEqual((result['a'], result['b'], result['path']), (7, 9, 1))
        self.assertEqual(codeword.wheel_word(7, 9, 1), result['word'])

    def test_incomplete_templates_abstain(self):
        width, height = 320, 220
        rgb = _frame(width, height, GLYPHS + PATH)
        mask = codeword.bitmap_rgb(rgb, width, height, 'rune')
        result = codeword.recognize_wheel(mask, [])
        self.assertFalse(result['confident'])
        self.assertIn('incomplete', result['reason'])

    def test_missing_second_rune_abstains(self):
        width, height = 320, 220
        rgb = _frame(width, height, GLYPHS[:1] + PATH)
        mask = codeword.bitmap_rgb(rgb, width, height, 'rune')
        result = codeword.recognize_wheel(mask, _template_set((10, 10), (6, 14)))
        self.assertFalse(result['confident'])
        self.assertIn('pair', result['reason'])

    def test_path_classification(self):
        def component(x, w, h):
            return {'x': x, 'y': 100, 'width': w, 'height': h}
        self.assertEqual(1, codeword._path_for([component(0, 10, 3), component(20, 3, 4), component(35, 3, 4),
                                                  component(55, 10, 3), component(75, 3, 4), component(90, 3, 4)]))
        self.assertEqual(0, codeword._path_for([component(0, 3, 4), component(15, 3, 4), component(30, 3, 4)]))


# --- Save-state round trip --------------------------------------------------

def _prepared_session(root: Path) -> tuple[GameSession, Path]:
    repo = root / 'repo'
    run = repo / 'resources' / 'oracle-runs' / 'testrun'
    (run / 'POOLRAD').mkdir(parents=True)
    (run / '.oracle-input-sha256').write_text('sha\n')
    (run / 'POOLRAD' / 'START.EXE').write_text('exe')
    data = root / 'data'
    data.mkdir()
    session = GameSession(repo, data)
    session.run_dir = run
    session.display = ':99'
    session.tmux_session = 'oracle'
    session.last_file.write_text('testrun\n')
    session._game_running = lambda: True
    session._focus_game = lambda: None
    return session, run


class SaveStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.session, self.run = _prepared_session(self.root)
        self.chords = []

        def fake_chord(combo):
            self.chords.append(combo)
            if combo == 'F12+s':
                saves = self.run / '.dosbox-saves'
                saves.mkdir(exist_ok=True)
                (saves / f'{self.session.active_slot}.sav').write_bytes(b'state-' + str(self.session.active_slot).encode())
                with (self.run / 'vp-dosbox-terminal.log').open('a') as log:
                    log.write(f'Saved. (Slot {self.session.active_slot})\n')
            elif combo == 'F12+l':
                with (self.run / 'vp-dosbox-terminal.log').open('a') as log:
                    log.write(f'Loaded. (Slot {self.session.active_slot})\n')

        self.session._chord = fake_chord
        self.session._wait_for_game_start = lambda timeout=20.0: True

    def test_save_list_load_round_trip_with_tags(self):
        first = self.session.savestate('Sokal Keep first floor')
        self.assertEqual(1, first['slot'])
        self.assertEqual('Sokal Keep first floor', first['tag'])
        self.assertTrue((self.run / '.dosbox-saves' / '1.sav').is_file())
        second = self.session.savestate('Kobold Caves')
        self.assertEqual(2, second['slot'])
        self.assertEqual(['F12+period'], [c for c in self.chords if c == 'F12+period'])
        self.assertEqual({1, 2}, {s['slot'] for s in self.session.list_states()['states']})
        self.chords.clear()
        loaded = self.session.loadstate(1)
        self.assertTrue(loaded['loaded'])
        self.assertTrue(loaded['verified'])
        self.assertEqual('Sokal Keep first floor', loaded['tag'])
        self.assertEqual(['F12+comma', 'F12+l'], self.chords)

    def test_slot_navigation_wraps_the_short_way(self):
        self.session._goto_slot(99)
        self.assertEqual(99, self.session.active_slot)
        self.assertEqual(['F12+comma'], self.chords)
        self.chords.clear()
        self.session._goto_slot(1)
        self.assertEqual(1, self.session.active_slot)
        self.assertEqual(['F12+period'], self.chords)

    def test_list_adopts_untagged_slot_files(self):
        saves = self.run / '.dosbox-saves'
        saves.mkdir(exist_ok=True)
        (saves / '7.sav').write_bytes(b'orphan')
        states = self.session.list_states()['states']
        self.assertEqual([7], [s['slot'] for s in states])
        self.assertEqual('slot 7', states[0]['tag'])

    def test_load_rejects_missing_state(self):
        with self.assertRaises(GameError):
            self.session.loadstate(4)

    def test_tampered_state_is_rejected(self):
        self.session.savestate('fresh')
        (self.run / '.dosbox-saves' / '1.sav').write_bytes(b'tampered')
        with self.assertRaises(GameError):
            self.session.loadstate(1)

    def test_autocodeword_types_only_when_two_frames_agree(self):
        width, height = 320, 220
        rgb = _frame(width, height, GLYPHS + PATH)
        templates = _template_set((10, 10), (6, 14))
        self.session.capture_frame = lambda inset=0: (rgb, width, height)
        typed = []
        self.session.type_text = lambda text, submit=True: typed.append((text, submit))
        result = self.session.recognize_codeword(templates)
        self.assertTrue(result['typed'])
        self.assertEqual(codeword.wheel_word(7, 9, 1), result['word'])
        self.assertEqual([(result['word'], True)], typed)

    def test_autocodeword_abstains_on_blank_frame(self):
        rgb = _frame(320, 220, [])
        self.session.capture_frame = lambda inset=0: (rgb, 320, 220)
        typed = []
        self.session.type_text = lambda text, submit=True: typed.append(text)
        result = self.session.recognize_codeword(_template_set((10, 10), (6, 14)))
        self.assertFalse(result['typed'])
        self.assertEqual([], typed)


# --- Endpoint wiring --------------------------------------------------------

class DosboxBinaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_default_uses_path_name(self):
        session = GameSession(self.root / 'repo', self.root / 'data')
        self.assertEqual('dosbox-x', session.dosbox_x)
        cmd = session._dosbox_command(self.root / 'run')
        self.assertEqual('dosbox-x', cmd[cmd.index('--chdir') + 2])

    def test_vp_dosbox_x_override_is_used(self):
        override = '/opt/dbx/dosbox-x-2026.10.01'
        with patch.dict(os.environ, {'VP_DOSBOX_X': override}):
            session = GameSession(self.root / 'repo', self.root / 'data')
        self.assertEqual(override, session.dosbox_x)
        cmd = session._dosbox_command(self.root / 'run')
        self.assertEqual(override, cmd[cmd.index('--chdir') + 2])
        self.assertNotIn('dosbox-x', cmd)


class LoadStateDialogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        run = self.root / 'repo' / 'resources' / 'oracle-runs' / 'testrun'
        (run / 'POOLRAD').mkdir(parents=True)
        (run / '.oracle-input-sha256').write_text('x')
        (run / 'POOLRAD' / 'START.EXE').write_text('x')
        data = self.root / 'data'
        data.mkdir()
        self.session = GameSession(self.root / 'repo', data)
        self.run = run
        self.session.run_dir = run
        self.session.display = ':99'
        self.session.tmux_session = 'oracle'
        self.session._game_running = lambda: True
        self.session._focus_game = lambda: None
        self.session._goto_slot = lambda slot: None
        self.session._log_size = lambda: 0
        self.log = run / 'vp-dosbox-terminal.log'
        saves = run / '.dosbox-saves'
        saves.mkdir(exist_ok=True)
        (saves / '1.sav').write_bytes(b'state')
        entry = {'slot': 1, 'tag': 't', 'created': '2026', 'session': None,
                 'size': 5, 'sha256': hashlib.sha256(b'state').hexdigest()}
        (run / 'vp-savestates.json').write_text(json.dumps({'version': 1, 'states': [entry]}))
        self.session._wait_for_game_start = lambda timeout=20.0: True

    def test_wait_for_load_status_markers(self):
        self.log.write_bytes(b'Loaded. (Slot 3)\n')
        self.assertEqual('loaded', self.session._wait_for_load_status(3, 0, 0.5))
        self.log.write_bytes(b'Aborted. Check your program name: START\n')
        self.assertEqual('mismatch', self.session._wait_for_load_status(1, 0, 0.5))
        self.log.write_bytes(b'Loaded. (Slot 2)\n')
        self.assertIsNone(self.session._wait_for_load_status(1, 0, 0.3))

    def test_game_started_marker(self):
        self.assertFalse(self.session._game_started())
        self.log.write_bytes(b"... Packed file is corrupt ...\n")
        self.assertTrue(self.session._game_started())

    def test_load_waits_for_game_start_then_loads(self):
        waited = []
        self.session._wait_for_game_start = lambda timeout=20.0: waited.append(timeout) or True
        chords = []
        self.session._chord = lambda combo: chords.append(combo)
        self.session._wait_for_load_status = lambda slot, offset, timeout=8.0: 'loaded'
        result = self.session.loadstate(1)
        self.assertTrue(result['verified'])
        self.assertEqual(1, len(waited))
        self.assertEqual(['F12+l'], chords)

    def test_load_refused_before_game_start(self):
        self.session._game_started = lambda: False
        self.session._wait_for_game_start = lambda timeout=20.0: False
        with self.assertRaises(GameError):
            self.session.loadstate(1)

    def test_load_mismatch_raises(self):
        self.session._game_started = lambda: True
        self.session._wait_for_game_start = lambda timeout=20.0: True
        self.session._chord = lambda combo: None
        self.session._wait_for_load_status = lambda slot, offset, timeout=8.0: 'mismatch'
        with self.assertRaises(GameError):
            self.session.loadstate(1)


class FakeGame:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def list_states(self):
        self.calls.append(('list',))
        return {'run_name': 'testrun', 'states': [{'slot': 1, 'tag': 'keep', 'created': '2026-10-19T00:00:00Z', 'size': 10}]}

    def savestate(self, tag):
        self.calls.append(('save', tag))
        if self.error:
            raise self.error
        return {'slot': 1, 'tag': tag}

    def loadstate(self, slot):
        self.calls.append(('load', slot))
        return {'slot': slot, 'loaded': True, 'verified': True}

    def recognize_codeword(self, templates):
        self.calls.append(('auto', len(templates)))
        return {'confident': True, 'typed': True, 'word': 'WYVERN', 'a': 1, 'b': 2, 'path': 0}


class GameEndpointTests(unittest.TestCase):
    def test_endpoints_dispatch_to_the_game_session(self):
        fake = FakeGame()
        with patch.object(server, 'GAME', fake), patch.object(server.codeword, 'templates_cached', return_value=[]):
            self.assertEqual('testrun', server.game_states('owner')['run_name'])
            self.assertEqual({'slot': 1, 'tag': 'x'}, server.game_savestate(server.GameSaveState(tag='x'), 'owner'))
            self.assertTrue(server.game_loadstate(server.GameLoadState(slot=2), 'owner')['loaded'])
            self.assertTrue(server.game_autocodeword('owner')['typed'])
        self.assertEqual([('list',), ('save', 'x'), ('load', 2), ('auto', 0)], fake.calls)

    def test_game_errors_become_400(self):
        fake = FakeGame(error=GameError('Poolrad is not running'))
        with patch.object(server, 'GAME', fake):
            with self.assertRaises(HTTPException) as failure:
                server.game_savestate(server.GameSaveState(tag='x'), 'owner')
        self.assertEqual(400, failure.exception.status_code)


if __name__ == '__main__':
    unittest.main()
