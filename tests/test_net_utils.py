import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

import requests

from updater.net_utils import download_with_retries


class _Response:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def close(self): pass

    def iter_content(self, chunk_size):
        yield self.content


class NetworkRetryTests(unittest.TestCase):
    def test_response_closed_on_success_http_error_and_cancel(self):
        for outcome in ("success", "http_error", "cancel"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                response = _Response(b"data", 404 if outcome == "http_error" else 200)
                checks = iter((False, outcome == "cancel"))
                with patch("updater.net_utils.requests.get", return_value=response), \
                        patch.object(response, "close") as close:
                    ok, error = download_with_retries(
                        "https://example/file", os.path.join(directory, "file"),
                        cancel_check=lambda: next(checks, False),
                    )
                self.assertEqual(ok, outcome == "success")
                close.assert_called_once()
                if outcome == "cancel":
                    self.assertEqual(error, "отменено")

    def test_retries_connection_error_then_verifies_download(self):
        payload = b"verified"
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "file.part")
            with patch(
                "updater.net_utils.requests.get",
                side_effect=[requests.ConnectionError("broken"), _Response(payload)],
            ) as get, patch("updater.net_utils._retry_delay", return_value=True):
                ok, error = download_with_retries(
                    "https://example/file",
                    target,
                    expected_size=len(payload),
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                )

            self.assertTrue(ok, error)
            self.assertEqual(get.call_count, 2)
            with open(target, "rb") as downloaded:
                self.assertEqual(downloaded.read(), payload)

    def test_does_not_retry_4xx_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "file.part")
            with open(target, "wb") as partial:
                partial.write(b"old")
            with patch(
                "updater.net_utils.requests.get", return_value=_Response(status_code=404)
            ) as get:
                ok, error = download_with_retries("https://example/missing", target)

            self.assertFalse(ok)
            self.assertIn("HTTP", error)
            self.assertEqual(get.call_count, 1)
            self.assertFalse(os.path.exists(target))

    def test_cancel_during_retry_delay_stops_next_attempt(self):
        cancelled = False

        def delay(_attempt, _cancel_check):
            nonlocal cancelled
            cancelled = True
            return False

        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "file.part")
            with patch(
                "updater.net_utils.requests.get",
                side_effect=requests.ConnectionError("broken"),
            ) as get, patch("updater.net_utils._retry_delay", side_effect=delay):
                ok, error = download_with_retries(
                    "https://example/file", target, cancel_check=lambda: cancelled
                )

            self.assertFalse(ok)
            self.assertEqual(error, "отменено")
            self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
