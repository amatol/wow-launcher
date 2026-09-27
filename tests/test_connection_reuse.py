"""Проверки повторного использования реальных HTTP/1.1-соединений."""
import hashlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests

from config import Config
from updater.addons import AddonEntry, AddonFile, install_selected
from updater.http_updater import HTTPUpdater
from updater.manifest import Manifest
from updater.net_utils import download_with_retries


PAYLOAD = b"verified file contents"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class Server(ThreadingHTTPServer):
    connections = 0

    def get_request(self):
        connection = super().get_request()
        self.connections += 1
        return connection


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        if self.path == "/close":
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *args):
        pass


class ConnectionReuseTests(unittest.TestCase):
    def setUp(self):
        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def test_client_files_share_one_connection(self):
        manifest = Manifest.from_dict({"version": "20260927", "files": [
            {"path": name, "http_url": self.url + "/" + name,
             "size": len(PAYLOAD), "sha256": DIGEST}
            for name in ("one", "two", "three")
        ]})
        updater = HTTPUpdater(str(self.root), manifest)
        self.assertEqual(updater.apply_all(manifest.files), (True, 3))
        self.assertEqual(self.server.connections, 1)
        for name in ("one", "two", "three"):
            self.assertEqual((self.root / name).read_bytes(), PAYLOAD)
        self.assertFalse(list(self.root.glob(".dw_dl_*")))

    def test_selected_addons_share_one_connection_across_packages(self):
        entries = [AddonEntry(name, "1", folders=[name], files=[
            AddonFile(f"{name}/{filename}", self.url + "/" + filename, DIGEST, len(PAYLOAD))
            for filename in (name + ".toc", "main.lua")
        ], size=2 * len(PAYLOAD)) for name in ("First", "Second")]
        with patch.object(Config, "ADDONS_DIR", str(self.root / "AddOns")), \
                patch.object(Config, "ADDONS_STATE_FILE", str(self.root / "state.json")):
            self.assertEqual(install_selected(entries), (True, 2, []))
        self.assertEqual(self.server.connections, 1)
        for entry in entries:
            for item in entry.files:
                self.assertEqual((self.root / "AddOns" / item.path).read_bytes(), PAYLOAD)

    def test_server_closure_opens_new_connection(self):
        with requests.Session() as session:
            for name in ("close", "next", "last"):
                ok, error = download_with_retries(
                    self.url + "/" + name, str(self.root / name),
                    expected_size=len(PAYLOAD), expected_sha256=DIGEST, session=session,
                )
                self.assertTrue(ok, error)
        self.assertEqual(self.server.connections, 2)

    def test_update_exception_closes_session_and_cleans_staging(self):
        updater = HTTPUpdater(str(self.root), Manifest.from_dict({
            "version": "20260927", "files": [],
        }))
        updater._get_tmp_dir()
        with patch("updater.http_updater.requests.Session.close") as close, \
                patch("updater.http_updater.remove_obsolete_files", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                updater.apply_all([])
        close.assert_called_once()
        self.assertFalse(list(self.root.glob(".dw_dl_*")))


if __name__ == "__main__":
    unittest.main()
