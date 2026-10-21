"""Изоляция режима, проверка файлов, продолжение загрузки и отказ при ошибках."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from config import Config
from core.survivors import SurvivorsInstaller, Cancelled, validate_manifest, launch_survivors


def sample():
    files = {'warcraft-survivors.exe': b'MZgame', 'VCRUNTIME140.dll': b'MZruntime', 'Data/terrain.MPQ': b'terrain', 'Data/patch.MPQ': b'patch'}
    return files, {'version': '20261021', 'files': [
        {'path': path, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
         'http_url': Config.SURVIVORS_BASE_URL + '/releases/20261021/files/' + path}
        for path, data in files.items()
    ]}


def response(data=b'', status=200, headers=None):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = headers or {}
    result.iter_content.return_value = [data]
    result.content = b'{}'
    return result


class SurvivorsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.installer = SurvivorsInstaller(self.parent)
        self.files, self.data = sample()

    def test_manifest_rejects_unsafe_and_unrelated_paths(self):
        for path in ('../Wow.exe', '/Wow.exe', 'C:/Wow.exe', 'Wow.exe', 'profiles/USER/save', 'Data/../../Wow.exe'):
            with self.subTest(path=path):
                self.data['files'][0]['path'] = path
                with self.assertRaises(ValueError):
                    validate_manifest(self.data)

    def test_manifest_requires_hash_and_same_https_origin(self):
        for key, value in (('http_url', 'http://example.test/a'), ('http_url', 'https://evil.test/a'), ('sha256', '')):
            with self.subTest(key=key):
                _, data = sample()
                data['files'][0][key] = value
                with self.assertRaises(ValueError):
                    validate_manifest(data)

    def test_case_insensitive_duplicate_and_removals_rejected(self):
        self.data['files'].append(dict(self.data['files'][-1], path='Data/patch.mpq'))
        with self.assertRaises(ValueError):
            validate_manifest(self.data)
        _, data = sample()
        data['removed_files'] = ['Wow.exe']
        with self.assertRaises(ValueError):
            validate_manifest(data)

    def test_install_checks_every_file_and_preserves_wotlk(self):
        (self.parent / 'Wow.exe').write_bytes(b'original-wow')
        meta = response()
        meta.json.return_value = self.data
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = [meta] + [response(data) for data in self.files.values()]
        with patch('core.survivors.requests.Session', return_value=session):
            root = self.installer.install()
        for path, data in self.files.items():
            self.assertEqual((root / path).read_bytes(), data)
        self.assertEqual((self.parent / 'Wow.exe').read_bytes(), b'original-wow')
        self.assertEqual((root / '.version').read_text(), '20261021')
        session.get.side_effect = [meta]
        with patch('core.survivors.requests.Session', return_value=session):
            self.installer.install()
        self.assertEqual(session.get.call_count, 6)

    def test_resume_partial_and_validate_range(self):
        self.installer.root.mkdir()
        entry = validate_manifest(self.data).files[0]
        partial = self.installer.root / '.downloads' / (entry.sha256 + '.part')
        partial.parent.mkdir()
        partial.write_bytes(b'MZ')
        session = MagicMock()
        session.get.return_value = response(b'game', 206, {'Content-Range': 'bytes 2-5/6'})
        self.installer._download(session, entry, 0, 6)
        self.assertEqual((self.installer.root / entry.path).read_bytes(), b'MZgame')
        self.assertEqual(session.get.call_args.kwargs['headers']['Range'], 'bytes=2-')

    def test_bad_range_and_hash_do_not_replace_existing_file(self):
        self.installer.root.mkdir()
        entry = validate_manifest(self.data).files[0]
        target = self.installer.root / entry.path
        target.write_bytes(b'old')
        session = MagicMock()
        for result in (response(b'MZgame', 206, {'Content-Range': 'bytes 1-6/7'}), response(b'broken')):
            session.get.return_value = result
            with self.assertRaises(ValueError):
                self.installer._download(session, entry, 0, 6)
            self.assertEqual(target.read_bytes(), b'old')

    def test_cancel_never_launches_or_writes_version(self):
        installer = SurvivorsInstaller(self.parent, cancelled=lambda: True)
        with self.assertRaises(Cancelled):
            installer.install()
        self.assertFalse(installer.root.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink fixture')
    def test_symlink_cannot_escape_mode_directory(self):
        self.installer.root.mkdir()
        (self.installer.root / 'Data').symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.installer._safe('Data/terrain.MPQ')

    def test_launch_isolated_environment_and_no_credentials(self):
        self.installer.root.mkdir()
        with patch.dict(os.environ, {'WOW_PASS': 'secret', 'WOW_CAPTURE': '1', 'BENILLA_HOME': 'wrong'}), patch.object(subprocess, 'Popen') as popen:
            launch_survivors(self.installer.root, 'TESTUSER')
        kwargs = popen.call_args.kwargs
        self.assertNotIn('WOW_PASS', kwargs['env'])
        self.assertNotIn('WOW_CAPTURE', kwargs['env'])
        self.assertEqual(kwargs['env']['WOW_DATA'], str(self.installer.root / 'Data'))
        profile = hashlib.sha256(b'TESTUSER').hexdigest()[:24]
        self.assertEqual(kwargs['env']['BENILLA_HOME'], str(self.installer.root / 'profiles' / profile))


if __name__ == '__main__':
    unittest.main()
