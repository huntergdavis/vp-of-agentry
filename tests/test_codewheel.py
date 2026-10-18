"""Private artwork is served only through authenticated, allowlisted routes."""

import asyncio
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

server = importlib.import_module('server.app')


class CodewheelRoutesTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        override = patch.object(server, 'CODEWHEEL_DIR', self.root)
        override.start(); self.addCleanup(override.stop)
        (self.root / 'esp01.gif').write_bytes(b'GIF89a')

    def test_only_allowlisted_files_and_no_symlinks(self):
        for filename in ('../auth.json', 'auth.json', 'esp00.gif', 'esp37.gif', 'det99.gif', 'esp1.gif', 'esp01.png', '/esp01.gif'):
            with self.subTest(filename=filename), self.assertRaises(HTTPException) as failure:
                server.game_codewheel_image(filename, 'owner')
            self.assertEqual(failure.exception.status_code, 404)
        (self.root / 'det01.gif').symlink_to(self.root / 'esp01.gif')
        with self.assertRaises(HTTPException):
            server.game_codewheel_image('det01.gif', 'owner')
        with self.assertRaises(HTTPException):
            server.game_codewheel_image('esp36.gif', 'owner')

    def test_serves_private_gif_with_nonpersistent_headers(self):
        response = server.game_codewheel_image('esp01.gif', 'owner')
        self.assertEqual(response.path, self.root / 'esp01.gif')
        self.assertEqual(response.media_type, 'image/gif')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(response.headers['cross-origin-resource-policy'], 'same-origin')

    def test_auth_and_origin_checked_before_file_access(self):
        async def request(headers):
            sent = []
            async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
            async def send(message): sent.append(message)
            await server.app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                              'method': 'GET', 'scheme': 'http', 'path': '/api/game/codewheel/esp01.gif',
                              'raw_path': b'/api/game/codewheel/esp01.gif', 'query_string': b'',
                              'server': ('localhost', 80), 'client': ('127.0.0.1', 1234),
                              'headers': [(b'host', b'localhost'), *headers]}, receive, send)
            return sent[0]['status']
        with patch.object(server, '_auth_record', return_value={'token': 'synthetic-test-token'}):
            self.assertEqual(asyncio.run(request([])), 401)
            auth = [(b'authorization', b'Bearer synthetic-test-token')]
            self.assertEqual(asyncio.run(request(auth + [(b'origin', b'http://elsewhere')])), 403)
            self.assertEqual(asyncio.run(request(auth)), 200)


if __name__ == '__main__':
    unittest.main()
