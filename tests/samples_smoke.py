"""Verify format templates, undo, shortcuts and live footer statistics."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(message)

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-samples-") as temporary:
        folder = Path(temporary)
        window = ReaderWindow(settings_path=folder / "settings.ini", restore_session=False)
        window.resize(1320, 900)
        window.show()

        def js(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(15)
            assert values, script
            return values[0]

        def wait(script):
            deadline = time.monotonic() + 20
            while not js(script):
                assert time.monotonic() < deadline, (script, errors)
                QTest.qWait(30)

        def key(value, modifiers=Qt.KeyboardModifier.NoModifier):
            QTest.keyClick(window.view.focusProxy() or window.view, value, modifiers)
            QTest.qWait(80)

        field = "document.querySelector('.source-editor:not([hidden])')"
        try:
            wait("!!window.readerApp && document.fonts.status==='loaded'")
            assert js("document.getElementById('status-cursor').hidden")
            for format_name in ("Markdown", "HTML", "JSON", "YAML", "XML", "CONF", "LOG", "Word"):
                window.bridge.newDocument(format_name)
                wait(
                    f"document.getElementById('document-format').textContent==={json.dumps(format_name)} && !!{field}"
                )
                assert js("document.getElementById('file-size').textContent==='0 B'")
                js("document.getElementById('insert-sample').click()")
                wait(field + ".value.length>20")
                source = js(field + ".value")
                wait("document.getElementById('preview-status').textContent==='Live preview'")
                assert (
                    js("document.getElementById('line-count').textContent")
                    == f"{len(source.splitlines()) + 1} lines"
                )
                assert (
                    js("document.getElementById('file-size').textContent")
                    == f"{len(source.encode())} B"
                )
                key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
                wait(field + ".value===''")
                js(field + ".focus()")
                key(
                    Qt.Key.Key_Space,
                    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
                )
                wait(field + ".value===" + json.dumps(source))
                key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
                wait(field + ".value===''")
                abbreviation = "doc" if format_name == "HTML" else "sample"
                js(
                    field
                    + f".focus();document.execCommand('insertText',false,{json.dumps(abbreviation)})"
                )
                key(Qt.Key.Key_Tab)
                wait(field + ".value===" + json.dumps(source))
                key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
                wait(field + ".value===" + json.dumps(abbreviation))
                print("PASS: sample button, shortcut, Tab and undo", format_name, flush=True)

            window.bridge.newDocument("Markdown")
            wait("document.getElementById('document-format').textContent==='Markdown'")
            js(field + ".focus();document.execCommand('insertText',false,'سلام 😀 world\\n')")
            wait("document.getElementById('word-count').textContent==='2 words'")
            assert js("document.getElementById('line-count').textContent==='2 lines'")
            assert js("document.getElementById('status-cursor').textContent==='Ln 2, Col 1'")
            assert js("document.getElementById('file-size').textContent==='20 B'")
            path = folder / "unicode.md"
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName", return_value=(str(path), "")
            ):
                js("document.getElementById('save-button').click()")
                wait("document.getElementById('save-status').textContent==='Saved'")
            assert path.stat().st_size == 20
            js("document.getElementById('read-mode').click()")
            assert js("document.getElementById('line-count').textContent==='2 lines'")
            assert js("document.getElementById('file-size').textContent==='20 B'")
            js("document.getElementById('status-cursor').click()")
            assert js("document.getElementById('go-to-line-dialog').open")
            key(Qt.Key.Key_Escape)
            window.resize(1000, 700)
            js("document.getElementById('edit-mode').click()")
            QTest.qWait(200)
            assert js("document.documentElement.scrollWidth<=innerWidth")
            window.grab().save(str(ROOT / "artifacts" / "editor-footer.png"))
            assert not errors, errors
            print("PASS: live Unicode counts, saved file size and footer navigation", flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
