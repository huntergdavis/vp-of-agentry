import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server.gameplay import GameError, GameSession


class PlayBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def session(self):
        return GameSession(self.root, self.root / 'data')

    def fixture(self):
        hybrid = self.root / 'resources/hybrid'
        (hybrid / 'bin').mkdir(parents=True)
        binary = hybrid / 'bin/dosbox-x'
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o700)
        (hybrid / 'registry_all.tsv').write_text('RES_0709_01DF\t01DF\t1\t00\tff\tunique\n')
        (hybrid / 'play-dispatch.txt').write_text('RES_0709_01DF\n')
        run = self.root / 'run'
        run.mkdir()
        return run

    def test_original_default_and_override(self):
        os.environ['VP_DOSBOX_X'] = '/original/dosbox-x'
        s = self.session()
        self.assertEqual(s.play_build, 'original')
        self.assertEqual(s.dosbox_x, '/original/dosbox-x')
        self.assertEqual(s._play_environment(self.root), {})
        self.assertEqual(s._dosbox_command(self.root)[-1], 'START')
        self.assertNotIn('cpu core=normal', s._dosbox_command(self.root))

    def test_invalid_flag_rejected(self):
        os.environ['VP_PLAY_BUILD'] = 'replacment'
        with self.assertRaisesRegex(GameError, 'VP_PLAY_BUILD'):
            self.session()

    def test_replacement_sets_route_and_copies_registry(self):
        run = self.fixture()
        os.environ.update(VP_PLAY_BUILD='replacement', VP_DOSBOX_X='/original/dosbox-x')
        s = self.session()
        env = s._play_environment(run)
        self.assertEqual(env['PR_HYBRID_DISPATCH'], 'RES_0709_01DF')
        self.assertEqual(env['PR_HYBRID_BUS_MODE'], 'route')
        self.assertTrue(Path(env['PR_HYBRID_REGISTRY']).is_file())
        self.assertIn('cpu core=normal', s._dosbox_command(run))
        self.assertEqual(s._dosbox_command(run)[-1], 'START')
        self.assertNotEqual(s.dosbox_x, '/original/dosbox-x')

    def test_missing_replacement_fails(self):
        os.environ['VP_PLAY_BUILD'] = 'replacement'
        with self.assertRaisesRegex(GameError, 'binary'):
            self.session()._play_environment(self.root)

    def test_unknown_or_duplicate_dispatch_fails(self):
        run = self.fixture()
        os.environ['VP_PLAY_BUILD'] = 'replacement'
        for text in ('RES_0000_0000', 'RES_0709_01DF,RES_0709_01DF', '', 'RES_0709_01DF;echo oops'):
            with self.subTest(text=text):
                (self.root / 'resources/hybrid/play-dispatch.txt').write_text(text)
                with self.assertRaisesRegex(GameError, 'unique registry'):
                    self.session()._play_environment(run)

    def test_original_clears_inherited_and_retained_harness_controls(self):
        env = dict.fromkeys(('DISPLAY', 'XAUTHORITY', 'SDL_AUDIODRIVER',
                             'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'), 'synthetic')
        env.update(PR_HYBRID_SEED_PIN='12345678', PR_HYBRID_FUTURE_TEST='bad', PR_PARITY_PREFIX='bad')
        args = GameSession._launch_env_args(env, {})
        for key in ('PR_HYBRID_DISPATCH', 'PR_HYBRID_REGISTRY', 'PR_HYBRID_SEED_PIN',
                    'PR_HYBRID_FUTURE_TEST', 'PR_PARITY_PREFIX', 'PR_PARITY_TARGET'):
            self.assertEqual(args[args.index(key) - 1], '-u')
        self.assertFalse(any(x.startswith('PR_') and '=' in x for x in args))


if __name__ == '__main__':
    unittest.main()
