"""Распознавание ручных установок и пользовательский путь обновления."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from config import Config
from updater.addons import AddonEntry, AddonFile, inspect_addon, install_selected
from ui.addons_dialog import AddonsDialog, AddonsFetchWorker
from ui.main_window import MainWindow


class AddonsDetectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.addons = self.root / 'AddOns'
        self.state = self.root / '.launcher_addons'
        for attr, value in [('ADDONS_DIR', self.addons), ('ADDONS_STATE_FILE', self.state)]:
            item = patch.object(Config, attr, str(value))
            item.start()
            self.addCleanup(item.stop)
        self.payload = b'## Interface: 30300\n## Version: unrelated-upstream-version\n'
        self.entry = AddonEntry('Package', '20261012', folders=['Core', 'Extra'], files=[
            AddonFile(f'{folder}/{folder}.toc', f'https://example/{folder}.toc',
                      hashlib.sha256(self.payload).hexdigest(), len(self.payload))
            for folder in ['Core', 'Extra']
        ], size=len(self.payload) * 2)

    def write(self, folder, payload=None):
        target = self.addons / folder / f'{folder}.toc'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.payload if payload is None else payload)

    def test_current_manual_install_needs_no_state_or_download(self):
        self.write('Core')
        self.write('Extra')
        inspect_addon(self.entry)
        self.assertTrue(self.entry.installed)
        self.assertFalse(self.entry.update_available)
        self.assertEqual(self.entry.installed_version, '20261012')
        self.assertFalse(self.state.exists())

    def test_manual_old_and_partial_packages_are_installed_with_update(self):
        self.write('Core', b'old')
        inspect_addon(self.entry)
        self.assertTrue(self.entry.installed)
        self.assertTrue(self.entry.update_available)
        self.assertIsNone(self.entry.installed_version)

    def test_stale_state_and_empty_folders_do_not_mean_installed(self):
        self.state.write_text(json.dumps({'Package': {'version': '20261001'}}))
        (self.addons / 'Core').mkdir(parents=True)
        inspect_addon(self.entry)
        self.assertFalse(self.entry.installed)
        self.assertFalse(self.entry.update_available)
        self.assertIsNone(self.entry.installed_version)

    def test_same_version_marker_cannot_hide_modified_files(self):
        self.write('Core', b'broken')
        self.write('Extra')
        self.state.write_text(json.dumps({'Package': {'version': '20261012'}}))
        inspect_addon(self.entry)
        self.assertTrue(self.entry.update_available)
        self.assertIsNone(self.entry.installed_version)

    def test_previous_version_is_reported_when_files_differ(self):
        self.write('Core', b'old')
        self.state.write_text(json.dumps({'Package': '20261001'}))
        inspect_addon(self.entry)
        self.assertTrue(self.entry.update_available)
        self.assertEqual(self.entry.installed_version, '20261001')

    def test_malformed_state_does_not_break_manual_detection(self):
        self.write('Core', b'old')
        for value in ['[]', 'null', '{broken']:
            self.state.write_text(value)
            inspect_addon(self.entry)
            self.assertTrue(self.entry.installed)
            self.assertTrue(self.entry.update_available)

    def test_manual_update_replaces_only_package_and_becomes_current(self):
        self.write('Core', b'old')
        self.write('Unrelated', b'custom')
        saved_variables = self.root / 'WTF' / 'SavedVariables.lua'
        saved_variables.parent.mkdir()
        saved_variables.write_bytes(b'user settings')
        def download(**kwargs):
            Path(kwargs['dest_path']).write_bytes(self.payload)
            return True, ''
        with patch('updater.net_utils.download_with_retries', side_effect=download):
            ok, count, errors = install_selected([self.entry])
        self.assertEqual((ok, count, errors), (True, 1, []))
        inspect_addon(self.entry)
        self.assertFalse(self.entry.update_available)
        self.assertEqual(self.entry.installed_version, '20261012')
        self.assertEqual((self.addons / 'Unrelated/Unrelated.toc').read_bytes(), b'custom')
        self.assertEqual(saved_variables.read_bytes(), b'user settings')

    def test_failed_download_preserves_existing_package_and_update(self):
        self.write('Core', b'old')
        with patch('updater.net_utils.download_with_retries', return_value=(False, 'offline')):
            ok, count, errors = install_selected([self.entry])
        self.assertFalse(ok)
        self.assertEqual(count, 0)
        self.assertTrue(errors)
        self.assertEqual((self.addons / 'Core/Core.toc').read_bytes(), b'old')
        inspect_addon(self.entry)
        self.assertTrue(self.entry.update_available)


class AddonsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        item = patch('PyQt5.QtCore.QThread.start')
        item.start()
        self.addCleanup(item.stop)
        self.current = AddonEntry('Current', '2', installed=True, installed_version='2')
        self.old = AddonEntry('Old', '2', installed=True, update_available=True)
        self.missing = AddonEntry('Missing', '2')
        self.entries = [self.current, self.old, self.missing]
        self.dialog = AddonsDialog()
        self.addCleanup(self.dialog.deleteLater)

    def test_installed_checked_and_only_outdated_selected_for_download(self):
        self.dialog._on_addons_fetched(self.entries)
        self.assertEqual([r.checkbox.isChecked() for r in self.dialog.rows], [True, True, False])
        self.assertEqual(self.dialog._get_selected(), [self.old])
        self.assertEqual(self.dialog.btn_install.text(), 'Обновить')
        self.dialog.rows[2].checkbox.setChecked(True)
        self.assertEqual(self.dialog._get_selected(), [self.old, self.missing])
        self.assertEqual(self.dialog.btn_install.text(), 'Установить и обновить')

    def test_current_addon_is_not_reinstalled_and_deselect_does_not_uninstall(self):
        self.dialog._on_addons_fetched([self.current])
        self.assertTrue(self.dialog.rows[0].checkbox.isChecked())
        self.assertFalse(self.dialog.btn_install.isEnabled())
        with patch('ui.addons_dialog.AddonsInstallWorker') as worker:
            self.dialog._on_install()
            worker.assert_not_called()
        self.dialog._deselect_all()
        self.assertTrue(self.current.installed)

    def test_update_button_path_automatically_updates_only_installed_old_addons(self):
        dialog = AddonsDialog(auto_update=True)
        self.addCleanup(dialog.deleteLater)
        with patch('ui.addons_dialog.AddonsInstallWorker') as worker:
            dialog._on_addons_fetched(self.entries)
            worker.assert_called_once_with([self.old])
            worker.return_value.start.assert_called_once()
            self.assertFalse(dialog.btn_close.isEnabled())
            self.assertTrue(all(not row.checkbox.isEnabled() for row in dialog.rows))

    def test_refresh_keeps_checks_and_clears_update_after_success(self):
        self.dialog._on_addons_fetched(self.entries)
        self.old.installed_version = '2'
        self.old.update_available = False
        self.dialog._on_addons_fetched(self.entries)
        self.assertEqual([r.checkbox.isChecked() for r in self.dialog.rows], [True, True, False])
        self.assertEqual(self.dialog.rows[1].status_label.text(), 'Установлено: 2')
        self.assertFalse(self.dialog.btn_install.isEnabled())

    def test_network_failure_has_retry_and_does_not_autoinstall(self):
        with patch('ui.addons_dialog.fetch_addons_manifest', return_value=None):
            worker = AddonsFetchWorker()
            failures, results = [], []
            worker.failed.connect(failures.append)
            worker.fetched.connect(results.append)
            worker.run()
        self.assertEqual(len(failures), 1)
        self.assertEqual(results, [])
        self.dialog._on_fetch_failed(failures[0])
        self.assertFalse(self.dialog.btn_install.isEnabled())
        self.assertFalse(self.dialog.btn_retry.isHidden())
        self.assertTrue(self.dialog.btn_close.isEnabled())

    def test_main_button_reflects_updates_and_passes_auto_update(self):
        with patch.object(MainWindow, '_restore_window_geometry'):
            window = MainWindow()
        self.addCleanup(window.deleteLater)
        window._on_addons_checked(self.entries)
        self.assertEqual(window.btn_addons.text(), 'Обновить Аддоны')
        with patch('ui.main_window.AddonsDialog') as dialog:
            window.open_addons()
            dialog.assert_called_once_with(window, auto_update=True)
        window._on_addons_check_failed('offline')
        self.assertEqual(window.btn_addons.text(), 'Обновить Аддоны')
        window._on_addons_checked([self.current, self.missing])
        self.assertEqual(window.btn_addons.text(), 'Аддоны')

    def test_empty_catalog_clears_old_rows_and_notifies_main_window(self):
        self.dialog._on_addons_fetched(self.entries)
        changed = []
        self.dialog.addons_changed.connect(changed.append)
        self.dialog._on_addons_fetched([])
        self.assertEqual(self.dialog.rows, [])
        self.assertEqual(changed, [[]])
        self.assertFalse(self.dialog.btn_install.isEnabled())

    def test_mixed_action_fits_minimum_dialog(self):
        self.dialog._on_addons_fetched(self.entries)
        self.dialog._select_all()
        self.dialog.resize(680, 480)
        self.dialog.show()
        self.app.processEvents()
        button = self.dialog.btn_install
        self.assertLess(button.fontMetrics().horizontalAdvance(button.text()), button.width() - 20)

    def test_escape_during_install_does_not_close_dialog(self):
        self.dialog._on_addons_fetched(self.entries)
        self.dialog.show()
        self.dialog._set_busy(True)
        self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        self.dialog.close()
        self.assertTrue(self.dialog.isVisible())
        self.dialog._set_busy(False)
        self.dialog.reject()
        self.assertFalse(self.dialog.isVisible())


if __name__ == '__main__':
    unittest.main()
