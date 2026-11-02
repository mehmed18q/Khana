"""Check native HTTP bounds and cookie isolation using a local server."""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api_fixture import api_server
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QSslSocket
from PySide6.QtTest import QTest

from reader.api_requests import ApiRequests


def main():
    _app = QCoreApplication.instance() or QCoreApplication([])
    client = ApiRequests()
    results = []
    client.finished.connect(lambda raw: results.append(json.loads(raw)))
    assert QSslSocket.supportsSsl(), "HTTPS must be available"
    with api_server() as (url, received):

        def send(path, headers=None):
            identifier = str(len(results))
            client.send(
                "doc",
                identifier,
                json.dumps({"url": url + path, "method": "GET", "headers": headers or {}}),
            )
            deadline = time.monotonic() + 5
            while (
                not any(value["id"] == identifier for value in results)
                and time.monotonic() < deadline
            ):
                QTest.qWait(10)
            assert results and results[-1]["id"] == identifier
            return results[-1]

        assert send("/cookie")["status"] == 200
        assert send("/public")["status"] == 200 and "cookie" not in received[-1]["headers"]
        assert send("/public", {"Cookie": "explicit=token"})["status"] == 200
        assert received[-1]["headers"]["cookie"] == "explicit=token"
        assert send("/public")["status"] == 200 and "cookie" not in received[-1]["headers"]
        print("PASS: explicit cookies work without a shared cookie jar", flush=True)
        with patch("reader.api_requests.MAX_BYTES", 32):
            assert "Response exceeds" in send("/public")["error"]
        assert not client.pending
        with patch("reader.api_requests.TIMEOUT_MS", 50):
            assert "timed out" in send("/slow")["error"]
        assert not client.pending
        print("PASS: response limit and timeout release pending requests", flush=True)
        assert send("/public")["status"] == 200
        print("Native API transport smoke test passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
