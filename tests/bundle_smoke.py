"""Test the actual packaged executable via a temporary local DevTools session.

Run on a graphical desktop. Uses a temporary config folder and documents; the
packaged app runs outside the project with no Python environment variables.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtWebSockets import QWebSocket

ROOT = Path(__file__).resolve().parent.parent


def pump(seconds=0.02):
    QCoreApplication.processEvents()
    time.sleep(seconds)


class PackagedApp:
    def __init__(self, executable, folder, files=(), platform=None, extra_env=None):
        self.folder = folder
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = dict(os.environ)
        for key in [
            "PYTHONHOME",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
            "QTWEBENGINE_DISABLE_SANDBOX",
        ]:
            env.pop(key, None)
        env["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{port}"
        env["XDG_CONFIG_HOME"] = str(folder / "config")
        # The single-instance socket must also be isolated from the user's app.
        temporary = folder / "tmp"
        temporary.mkdir(exist_ok=True)
        env["TMPDIR"] = str(temporary)
        if platform:
            env["QT_QPA_PLATFORM"] = platform
        if extra_env:
            env.update(extra_env)
        self.log = (folder / "app.log").open("ab")
        self.process = subprocess.Popen(
            [str(executable), *map(str, files)],
            cwd=folder,
            env=env,
            stdout=self.log,
            stderr=self.log,
        )
        self.ws = QWebSocket()
        self.messages = {}
        self.exceptions = []
        self.counter = 0
        self.ws.textMessageReceived.connect(self.receive)
        try:
            deadline = time.monotonic() + 50
            page = None
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise AssertionError((folder / "app.log").read_text())
                try:
                    with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as result:
                        page = next((p for p in json.load(result) if p["type"] == "page"), None)
                except OSError:
                    pass
                if page:
                    break
                pump(0.1)
            assert page, "No bundled WebEngine page"
            connected = []
            self.ws.connected.connect(lambda: connected.append(True))
            self.ws.open(QUrl(page["webSocketDebuggerUrl"]))
            while not connected and time.monotonic() < deadline:
                pump()
            assert connected, self.ws.errorString()
            self.call("Runtime.enable")
            self.wait(
                "!!window.readerApp?.activeId && document.fonts.status==='loaded'",
                "bundled UI, fonts, native bridge and startup document load",
            )
        except BaseException:
            self.stop()
            raise

    def receive(self, raw):
        message = json.loads(raw)
        if "id" in message:
            self.messages[message["id"]] = message
        if message.get("method") == "Runtime.exceptionThrown":
            self.exceptions.append(message)

    def call(self, method, params=None):
        self.counter += 1
        identifier = self.counter
        self.ws.sendTextMessage(
            json.dumps({"id": identifier, "method": method, "params": params or {}})
        )
        deadline = time.monotonic() + 12
        while identifier not in self.messages and time.monotonic() < deadline:
            pump()
        assert identifier in self.messages, f"DevTools timed out: {method}"
        message = self.messages.pop(identifier)
        assert "error" not in message, message
        return message.get("result", {})

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        assert "exceptionDetails" not in result, result
        return result.get("result", {}).get("value")

    def wait(self, expression, label):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                print("PASS:", label, flush=True)
                return
            pump(0.08)
        raise AssertionError(
            f"{label}; {self.exceptions}; " + (self.folder / "app.log").read_text()
        )

    def stop(self):
        self.ws.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()

    def close(self):
        self.evaluate("readerApp.command('quit-request')")
        deadline = time.monotonic() + 10
        while self.process.poll() is None and time.monotonic() < deadline:
            pump()
        assert self.process.poll() == 0, "Bundled app did not exit cleanly"
        assert not self.exceptions, self.exceptions
        self.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=Path)
    args = parser.parse_args()
    executable = (
        args.executable
        or (
            ROOT / "dist/Khana"
            if (ROOT / "dist/Khana").exists()
            else ROOT / "build/onedir/Khana/Khana"
        )
    ).resolve()
    _app = QCoreApplication.instance() or QCoreApplication([])
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="khana-bundle-") as temp:
        folder = Path(temp)
        launch_path = executable
        if executable.parent.name == "dist":
            launch_path = folder / "app with spaces/Khana"
            launch_path.parent.mkdir()
            shutil.copy2(executable, launch_path)
        running = PackagedApp(launch_path, folder)
        try:
            assert running.evaluate(
                "document.getElementById('current-filename').textContent==='welcome.md'"
            )
            # Both changes must survive the next extraction of the one-file app.
            running.evaluate(
                "readerApp.settings.theme='dark'; readerApp.settings.fontSize=19; readerApp.preferences()"
            )
            running.close()
            config = folder / "config/Khana/Khana/settings.ini"
            assert config.is_file() and "dark" in config.read_text()
            source = (
                ROOT / "examples/tables-and-flowcharts.md"
            ).read_text() + '\n```python\nprint("سلام")\n```\n'
            md = folder / "سند test.md"
            md.write_text(source)
            html = folder / "page.html"
            html.write_text("<h1>سلام HTML</h1><p>English and فارسی</p>")
            running = PackagedApp(launch_path, folder, [html, md])
            running.wait(
                "document.getElementById('file-count').textContent==='2' && document.querySelectorAll('.diagram-frame[data-status=ready]').length===2",
                "CLI files, multiple flowcharts and all bundled Mermaid assets load",
            )
            assert running.evaluate(
                "readerApp.settings.theme==='dark' && readerApp.settings.fontSize===19"
            )
            assert running.evaluate("!!document.querySelector('code.language-python .nb')")
            assert running.evaluate(
                "document.querySelector('.diagram-surface').shadowRoot.querySelector('svg').getBoundingClientRect().width>100"
            )
            running.evaluate(
                "readerApp.setEditMode(true); document.querySelector('[data-format=table]').click(); document.getElementById('table-insert').click()"
            )
            running.wait(
                "document.querySelectorAll('#document table').length===2",
                "packaged table builder and live preview",
            )
            running.evaluate(
                "document.querySelector('[data-format=flowchart]').click(); document.getElementById('flow-insert').click()"
            )
            running.wait(
                "document.querySelectorAll('.diagram-frame[data-status=ready]').length===3",
                "packaged flowchart builder",
            )
            saved_source = running.evaluate(
                "document.querySelector('.source-editor:not([hidden])').value"
            )
            running.evaluate("readerApp.command('save')")
            running.wait(
                "document.getElementById('save-status').textContent==='Saved'",
                "packaged app saves edited documents",
            )
            assert md.read_text() == saved_source
            running.evaluate(
                "readerApp.setEditMode(false); document.querySelector('.diagram-frame').scrollIntoView({block:'center'})"
            )
            pump(0.3)
            screenshot = running.call("Page.captureScreenshot", {"format": "png"})
            tag = "onefile" if executable.parent.name == "dist" else "onedir"
            (artifacts / f"bundle-{tag}.png").write_bytes(base64.b64decode(screenshot["data"]))
            running.evaluate(
                "Array.from(document.querySelectorAll('.file-select')).find(b=>b.textContent.includes('page.html')).click()"
            )
            running.wait(
                "document.querySelector('#document h1')?.textContent.includes('سلام HTML')",
                "packaged HTML reader",
            )
            running.close()
            if os.environ.get("DISPLAY"):
                running = PackagedApp(launch_path, folder, platform="xcb")
                running.close()
                print("PASS: bundled X11 backend starts and closes cleanly", flush=True)
            print(f"Packaged executable passed: {executable}", flush=True)
        finally:
            running.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
