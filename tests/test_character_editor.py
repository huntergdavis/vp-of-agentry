"""Editor adapter contract tests. All records/profiles here are synthetic."""
import asyncio
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from server.character_editor import CopyRequest, EditorError, EditorStore, ProfileChoice, router


class FixtureResponse:
    def __init__(self, status, content, headers):
        self.status_code, self.content, self.headers = status, content, headers
        self.text = content.decode('utf-8', errors='replace')

    def json(self):
        return json.loads(self.content)


class ASGIFixtureClient:
    """Exercise the actual ASGI router without an optional HTTP client dependency."""
    def __init__(self, app):
        self.app = app

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, **kwargs):
        return self.request('POST', path, **kwargs)

    def request(self, method, path, *, json=None, files=None, content=None, headers=None):
        import json as json_module
        headers = dict(headers or {})
        body = content or b''
        if json is not None:
            body = json_module.dumps(json).encode()
            headers['content-type'] = 'application/json'
        if files:
            boundary = 'character-editor-fixture-boundary'
            body = b''
            for field, item in (files.items() if isinstance(files, dict) else files):
                name, data, *mime = item
                prefix = f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\nContent-Type: {mime[0] if mime else "application/octet-stream"}\r\n\r\n'
                body += prefix.encode() + data + b'\r\n'
            body += f'--{boundary}--\r\n'.encode()
            headers['content-type'] = f'multipart/form-data; boundary={boundary}'
        parsed = urlsplit(path)
        scope = dict(type='http', asgi={'version': '3.0'}, http_version='1.1', method=method,
                     scheme='http', path=parsed.path, raw_path=parsed.path.encode(),
                     query_string=parsed.query.encode(), root_path='', server=('fixture', 80),
                     client=('fixture', 1), headers=[(k.lower().encode(), v.encode()) for k, v in headers.items()])
        messages = []
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {'type': 'http.disconnect'}
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def send(message):
            messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        start = next(m for m in messages if m['type'] == 'http.response.start')
        return FixtureResponse(start['status'], b''.join(m.get('body', b'') for m in messages),
                               {k.decode(): v.decode() for k, v in start['headers']})


def synthetic_save():
    data = bytearray(285)
    data[0x10:0x16] = bytes([17, 12, 12, 17, 16, 15])
    data[0x98] = 1
    return bytes(data)


class FixtureStore(EditorStore):
    """Deterministic CLI contract double; never evidence of reference game editing."""
    def _run(self, payload, *, noop=False):
        source = Path(payload['source'])
        files = {p.name: p.read_bytes() for p in source.iterdir() if p.suffix in ('.SAV', '.ITM', '.SPC', '.DAT')}
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        characters = []
        for name, data in files.items():
            if not name.endswith('.SAV'):
                continue
            if len(data) != 285:
                raise EditorError('Synthetic invalid record')
            profiles = [dict(validation_profile='reference_strength_17_to_16', field='strength',
                             expected_before=17, value=16, eligible=data[16] == 17,
                             eligible_after_application=['reference_fighter_level_1_to_2']),
                        dict(validation_profile='reference_fighter_level_1_to_2', field='level',
                             expected_before=1, value=2, eligible=data[16] == 16 and data[0x98] == 1,
                             eligible_after_application=[])]
            for profile in profiles:
                profile.update(reason_unavailable=None if profile['eligible'] else 'Synthetic unmatched profile',
                               proof_scope='Synthetic browser/API fixture, not game evidence.', evidence='synthetic')
            characters.append(dict(file=name, sha256=hashes[name],
                                   current_values=dict(zip(['strength', 'intelligence', 'wisdom', 'dexterity', 'constitution', 'charisma'], data[16:22])),
                                   level_slots=list(data[0x96:0x9e]), reference_fighter_level=data[0x98],
                                   profiles=profiles, unsupported_fields='Other fields cannot be edited.'))
        if payload['operation'] == 'inspect':
            return dict(expected_source_hashes=hashes, characters=characters,
                        validation_scope=dict(game_validation='UNVERIFIED', game_build_loaded=None))
        destination = Path(payload['destination'])
        destination.mkdir()
        edited = {name: bytearray(data) for name, data in files.items()}
        for change in payload['changes']:
            edited[change['file']][16 if change['field'] == 'strength' else 0x98] = change['value']
        receipts = []
        for name, after in edited.items():
            target = destination / name
            target.write_bytes(after)
            offsets = [i for i, (a, b) in enumerate(zip(files[name], after)) if a != b]
            receipts.append(dict(file=str(target), source=str(source / name), changed_offsets=offsets,
                                 before_after_bytes=[dict(offset=i, before=files[name][i], after=after[i]) for i in offsets],
                                 before_sha256=hashes[name], after_sha256=hashlib.sha256(after).hexdigest(),
                                 byte_identical=not offsets, game_validation='UNVERIFIED', game_build_loaded=None))
        (destination / 'write-receipts.json').write_text(json.dumps(dict(files=receipts)))
        return dict(files_written=len(files), bytes_written=sum(map(len, files.values())),
                    byte_identical_files=sum(r['byte_identical'] for r in receipts))


class CharacterEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tool = self.root / 'edit_save.py'
        self.tool.write_text('# synthetic contract double')
        self.store = FixtureStore(self.root / 'editor', self.tool)
        app = FastAPI()
        app.include_router(router(self.store, lambda: 'fixture'))
        self.client = ASGIFixtureClient(app)
        self.addCleanup(self.client.close)

    def imported(self):
        result = self.client.post('/api/character-editor/imports', files=[
            ('files', ('CHRDATA1.SAV', synthetic_save(), 'application/octet-stream'))])
        self.assertEqual(200, result.status_code, result.text)
        return result.json()

    def request(self, source, profiles=()):
        return dict(source_id=source['id'], copy_name='Fixture copy',
                    expected_source_hashes=source['expected_source_hashes'],
                    profiles=[dict(file='CHRDATA1.SAV', validation_profile=p) for p in profiles])

    def test_import_noop_download_preserves_bytes_and_hides_private_paths(self):
        source = self.imported()
        copied = self.client.post('/api/character-editor/copies', json=self.request(source))
        self.assertEqual(200, copied.status_code, copied.text)
        result = copied.json()
        self.assertEqual('UNVERIFIED', result['game_validation'])
        self.assertIsNone(result['game_build_loaded'])
        self.assertNotIn(str(self.root), copied.text)
        self.assertEqual(1, result['byte_identical_files'])
        download = self.client.get(result['download_url'])
        self.assertEqual(200, download.status_code)
        with zipfile.ZipFile(io.BytesIO(download.content)) as zipped:
            self.assertEqual(synthetic_save(), zipped.read('CHRDATA1.SAV'))
            self.assertNotIn(str(self.root), zipped.read('write-receipts.json').decode())
        self.assertEqual(source['expected_source_hashes'], self.store.inspect(source['id'])['expected_source_hashes'])

    def test_ordered_reference_choices_are_derived_from_inspection_and_only_change_copy(self):
        source = self.imported()
        choices = ['reference_strength_17_to_16', 'reference_fighter_level_1_to_2']
        copied = self.client.post('/api/character-editor/copies', json=self.request(source, choices))
        self.assertEqual(200, copied.status_code, copied.text)
        result = copied.json()
        self.assertEqual([16, 0x98], result['receipt']['files'][0]['changed_offsets'])
        self.assertEqual(16, result['inspection']['characters'][0]['current_values']['strength'])
        self.assertEqual(2, result['inspection']['characters'][0]['reference_fighter_level'])
        self.assertEqual(source['expected_source_hashes'], self.store.inspect(source['id'])['expected_source_hashes'])

    def test_unknown_receipt_fields_never_reach_api_or_zip(self):
        # Extend the synthetic CLI output at each receipt level separately.
        # The supported fields mirror the accepted schema-1 CLI contract.
        run = self.store._run
        for level in ('top', 'file', 'byte_change', 'applied_change', 'rejected_change'):
            with self.subTest(level=level):
                source = self.imported()
                expected = {}
                marker = str(self.root / ('private-' + level))

                def extended_receipt(payload, *, noop=False):
                    report = run(payload, noop=noop)
                    if payload['operation'] == 'inspect':
                        return report
                    path = Path(payload['destination']) / 'write-receipts.json'
                    receipt = json.loads(path.read_text())
                    row = receipt['files'][0]
                    row.update(operation='edit_copy', size=len(synthetic_save()))
                    row['before_after_bytes'][0]['reason'] = 'Synthetic reference edit'
                    applied = dict(payload['changes'][0], index=0, offset=16,
                                   before_sha256=row['before_sha256'], after_sha256=row['after_sha256'],
                                   historical_evidence='docs/synthetic-reference.md',
                                   proof_scope='Synthetic receipt contract, not game evidence.')
                    receipt.update(schema_version=1, operation='edit_copy',
                                   applied_changes=[applied], rejected_changes=[],
                                   historical_reference_only=True, limits='Reference transitions only.')
                    if level == 'rejected_change':
                        # The pinned CLI emits an empty list. Exercise a future
                        # change row without permitting its unknown metadata.
                        receipt['rejected_changes'] = [dict(file='OTHER.SAV', field='strength')]
                    public = copy.deepcopy(receipt)
                    public.update(game_validation='UNVERIFIED', game_build_loaded=None)
                    public['files'][0]['file'] = public['files'][0]['source'] = 'CHRDATA1.SAV'
                    expected['receipt'] = public
                    targets = {'top': receipt, 'file': row,
                               'byte_change': row['before_after_bytes'][0],
                               'applied_change': applied}
                    target = receipt['rejected_changes'][0] if level == 'rejected_change' else targets[level]
                    target.update(private_path=marker, future_metadata={'nested_path': marker})
                    # A CLI extension must not promote a newly written copy.
                    receipt.update(game_validation='VERIFIED', game_build_loaded=marker)
                    row.update(game_validation='VERIFIED', game_build_loaded=marker)
                    path.write_text(json.dumps(receipt))
                    return report

                with patch.object(self.store, '_run', side_effect=extended_receipt):
                    copied = self.client.post('/api/character-editor/copies', json=self.request(
                        source, ['reference_strength_17_to_16']))
                self.assertEqual(200, copied.status_code, copied.text)
                result = copied.json()
                self.assertNotIn(marker, copied.text)
                self.assertEqual(expected['receipt'], result['receipt'])
                self.assertEqual([16], result['receipt']['files'][0]['changed_offsets'])
                self.assertEqual([{'offset': 16, 'before': 17, 'after': 16,
                                   'reason': 'Synthetic reference edit'}],
                                 result['receipt']['files'][0]['before_after_bytes'])
                downloaded = self.client.get(result['download_url'])
                self.assertEqual(200, downloaded.status_code)
                with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
                    public_bytes = archive.read('write-receipts.json')
                    self.assertNotIn(marker, public_bytes.decode())
                    self.assertEqual(expected['receipt'], json.loads(public_bytes))
                    edited = bytearray(synthetic_save())
                    edited[16] = 16
                    self.assertEqual(bytes(edited), archive.read('CHRDATA1.SAV'))
                self.assertEqual(source['expected_source_hashes'], self.store.inspect(source['id'])['expected_source_hashes'])

    def test_invalid_names_duplicate_files_and_bad_records_leave_no_registered_import(self):
        for files in [[('../CHRDATA1.SAV', synthetic_save())],
                      [('chrdata1.sav', synthetic_save()), ('CHRDATA1.SAV', synthetic_save())],
                      [('CHRDATA1.SAV', b'bad')]]:
            with self.subTest(names=[name for name, _ in files]):
                with self.assertRaises(EditorError):
                    self.store.import_files(files)
                self.assertEqual([], self.store.sources()['sources'])

    def test_stale_hash_unavailable_profile_and_arbitrary_offsets_are_refused(self):
        source = self.imported()
        body = self.request(source)
        body['expected_source_hashes'] = {}
        self.assertEqual(409, self.client.post('/api/character-editor/copies', json=body).status_code)
        body = self.request(source, ['reference_fighter_level_1_to_2'])
        self.assertEqual(400, self.client.post('/api/character-editor/copies', json=body).status_code)
        body = self.request(source)
        body['offset'] = 16
        self.assertEqual(422, self.client.post('/api/character-editor/copies', json=body).status_code)
        self.assertFalse((self.store.root / 'copies').exists())

    def test_authentication_guards_upload_list_inspect_copy_and_download(self):
        app = FastAPI()
        def deny():
            raise HTTPException(401, 'Fixture sign-in required')
        app.include_router(router(self.store, deny))
        with ASGIFixtureClient(app) as client:
            for path in ('/sources', '/sources/' + 'a' * 32, '/copies/' + 'a' * 32 + '/download'):
                self.assertEqual(401, client.get('/api/character-editor' + path).status_code)
            self.assertEqual(401, client.post('/api/character-editor/imports', files={'files': ('CHRDATA1.SAV', synthetic_save())}).status_code)
            self.assertEqual(401, client.post('/api/character-editor/copies', json=self.request({'id': 'a' * 32, 'expected_source_hashes': {}})).status_code)
        self.assertFalse(self.store.root.exists())

    def test_changed_output_is_not_downloaded(self):
        source = self.imported()
        result = self.store.copy(CopyRequest(**self.request(source)))
        folder, _ = self.store._lookup(result['id'])
        (folder / 'files/CHRDATA1.SAV').write_bytes(b'changed')
        self.assertEqual(409, self.client.get(result['download_url']).status_code)

    def test_cli_errors_do_not_expose_private_paths(self):
        store = EditorStore(self.root / 'other', self.tool)
        response = type('Result', (), {'returncode': 1, 'stdout': '', 'stderr': str(self.root / 'private-source')})()
        with patch('server.character_editor.subprocess.run', return_value=response) as run:
            with self.assertRaises(EditorError) as caught:
                store._run({'schema_version': 1, 'operation': 'inspect', 'source': str(self.root)})
            self.assertNotIn(str(self.root), str(caught.exception))
            self.assertNotIn('shell', run.call_args.kwargs)
            self.assertEqual(str(self.tool), run.call_args.args[0][1])


if __name__ == '__main__':
    unittest.main()
