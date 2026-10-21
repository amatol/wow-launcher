"""Первая установка с Яндекса, проверка архива и сохранение профилей."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from config import Config
from core.survivors import SurvivorsInstaller, Cancelled, validate_manifest
from tests.test_survivors import sample, response


class SurvivorsBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.installer = SurvivorsInstaller(self.temp.name)
        self.files, self.data = sample()
        self.manifest = validate_manifest(self.data)

    def archive(self, prefix='Survivors/', extra=None, replacements=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            for path, data in self.files.items():
                z.writestr(prefix + path, (replacements or {}).get(path, data))
            for name, data in (extra or {}).items():
                z.writestr(name, data)
        return stream.getvalue()

    def install(self, archive, responses=None):
        digest = hashlib.sha256(archive).hexdigest()
        meta = response(); meta.json.return_value = self.data
        session = MagicMock(); session.__enter__.return_value = session
        session.get.side_effect = [meta] + (responses or [response(archive)])
        with patch.object(Config, 'SURVIVORS_ARCHIVE_SIZE', len(archive)), patch.object(Config, 'SURVIVORS_ARCHIVE_SHA256', digest), patch('core.survivors.resolve_yandex_download', return_value=('https://example.test/archive', len(archive))) as resolve, patch('core.survivors.requests.Session', return_value=session):
            root = self.installer.install()
        return root, session, resolve

    def test_first_install_from_yandex_verifies_files_and_ignores_profiles(self):
        archive = self.archive(extra={'Survivors/profiles/other/config.toml': b'private', 'Survivors/Dreamworld.exe': b'foreign'})
        root, session, resolve = self.install(archive)
        resolve.assert_called_once_with(Config.SURVIVORS_ARCHIVE_PUBLIC_URL)
        self.assertEqual(session.get.call_count, 2)
        for path, data in self.files.items():
            self.assertEqual((root / path).read_bytes(), data)
        self.assertFalse((root / 'profiles').exists())
        self.assertFalse((root / 'Dreamworld.exe').exists())
        self.assertFalse((root / '.downloads/survivors-client.zip').exists())
        self.assertEqual((root / '.version').read_text(), self.manifest.version)

    def test_root_archive_and_updates_repair_outdated_file(self):
        archive = self.archive(prefix='', replacements={'warcraft-survivors.exe': b'oldexe'})
        root, session, _ = self.install(archive, [response(archive), response(self.files['warcraft-survivors.exe'])])
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual((root / 'warcraft-survivors.exe').read_bytes(), self.files['warcraft-survivors.exe'])

    def test_partial_archive_resumes_by_range(self):
        archive = self.archive()
        digest = hashlib.sha256(archive).hexdigest()
        partial = self.installer.root / '.downloads' / (digest + '.part')
        partial.parent.mkdir(parents=True);partial.write_bytes(archive[:10])
        root, session, _ = self.install(archive, [response(archive[10:], 206, {'Content-Range': f'bytes 10-{len(archive)-1}/{len(archive)}'})])
        self.assertEqual(session.get.call_args.kwargs['headers']['Range'], 'bytes=10-')
        self.assertTrue((root / '.version').exists())

    def test_existing_files_or_file_parts_skip_archive(self):
        self.installer.root.mkdir()
        for path, data in self.files.items():
            target = self.installer.root / path; target.parent.mkdir(exist_ok=True);target.write_bytes(data)
        profile = self.installer.root / 'profiles/me/settings'; profile.parent.mkdir(parents=True);profile.write_bytes(b'personal')
        meta = response(); meta.json.return_value = self.data
        session = MagicMock();session.__enter__.return_value = session;session.get.return_value=meta
        with patch('core.survivors.resolve_yandex_download') as resolve, patch('core.survivors.requests.Session', return_value=session):
            self.installer.install()
        resolve.assert_not_called();self.assertEqual(profile.read_bytes(),b'personal')
        self.assertEqual(session.get.call_count,1)
        for path in self.files: (self.installer.root/path).unlink()
        partial = self.installer.root / '.downloads' / (self.manifest.files[0].sha256+'.part')
        partial.parent.mkdir(exist_ok=True);partial.write_bytes(b'MZ')
        self.assertFalse(self.installer._needs_bootstrap(self.manifest))

    def test_bad_archive_hash_does_not_extract_or_mark_installed(self):
        with self.assertRaisesRegex(ValueError,'сумма'):
            self.install(self.archive(), [response(b'x'*len(self.archive()))])
        self.assertFalse((self.installer.root/'.version').exists())
        self.assertFalse((self.installer.root/'warcraft-survivors.exe').exists())

    def test_zip_traversal_and_duplicates_are_rejected_before_extracting(self):
        self.installer.root.mkdir()
        for name in ['../escape', 'Survivors/Data/../../escape', 'Survivors/C:/escape', 'Survivors/data/PATCH.mpq']:
            with self.subTest(name=name):
                archive=self.installer.root/'test.zip';archive.write_bytes(self.archive(extra={name:b'bad'}))
                with self.assertRaises(ValueError):self.installer._extract_archive(archive,self.manifest)
                self.assertFalse((self.installer.root/'warcraft-survivors.exe').exists())

    def test_cancellation_during_extraction_preserves_archive_and_profiles(self):
        self.installer.root.mkdir()
        archive=self.installer.root/'test.zip';archive.write_bytes(self.archive())
        self.installer.cancelled=lambda:True
        with self.assertRaises(Cancelled):self.installer._extract_archive(archive,self.manifest)
        self.assertTrue(archive.exists());self.assertFalse((self.installer.root/'.version').exists())

    def test_completed_archive_remains_usable_after_partial_extraction(self):
        archive = self.archive()
        target = self.installer.root / '.downloads/survivors-client.zip'
        target.parent.mkdir(parents=True); target.write_bytes(archive)
        # Первый файл мог быть установлен до отмены распаковки.
        (self.installer.root / 'warcraft-survivors.exe').write_bytes(self.files['warcraft-survivors.exe'])
        self.assertTrue(self.installer._needs_bootstrap(self.manifest))
        root, session, resolve = self.install(archive, [])
        resolve.assert_not_called()
        self.assertEqual(session.get.call_count, 1)
        self.assertTrue((root / 'Data/terrain.MPQ').is_file())

    def test_changed_yandex_archive_size_is_rejected(self):
        self.installer.root.mkdir()
        session=MagicMock()
        with patch('core.survivors.resolve_yandex_download',return_value=('https://example.test/archive',1)):
            with self.assertRaisesRegex(ValueError,'изменился'):self.installer._bootstrap(session,self.manifest)
        session.get.assert_not_called()
