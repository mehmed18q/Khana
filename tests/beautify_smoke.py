"""Format structured source through the desktop bridge, with undo and error recovery."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.source_formatting import beautify_source
from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(message)

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-format-") as temporary:
        folder = Path(temporary)
        samples = [
            ("json", '{"id":9007199254740993123,"name":"سلام","items":[1,2]}', '{"broken":}'),
            ("yaml", '# Keep\napp:\n     name: "سلام"\n     values: [1,2]\n', "values: [1,"),
            ("xml", "<r><name>سلام</name><values><v>1</v><v>2</v></values></r>", "<r><v></r>"),
        ]
        window = ReaderWindow(settings_path=folder / "settings.ini")
        window.showFullScreen()
        field = "document.querySelector('.source-editor:not([hidden])')"

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda result: values.append(result))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script[:100]
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            raise AssertionError(
                f"{label}: {errors}; "
                + str(evaluate("document.getElementById('toast').textContent"))
            )

        def click(identifier):
            evaluate(f"document.getElementById('{identifier}').click()")

        def edit(source):
            evaluate(
                field
                + ".value="
                + json.dumps(source)
                + ";"
                + field
                + ".dispatchEvent(new Event('input',{bubbles:true}))"
            )

        try:
            wait("!!window.readerApp?.activeId", "desktop loads")
            click("edit-mode")
            assert evaluate("document.getElementById('beautify-button').hidden")
            for suffix, source, invalid in samples:
                path = folder / ("sample." + suffix)
                path.write_text(source)
                window.bridge.load_paths([path])
                wait("readerApp.activeId===" + json.dumps(str(path)), "open " + suffix)
                click("edit-mode")
                assert evaluate(
                    "!document.getElementById('beautify-button').hidden && document.getElementById('format-toolbar').hidden"
                )
                expected = beautify_source(source, suffix.upper())
                if suffix == "json":
                    QTest.keyClick(
                        window.view.focusProxy() or window.view,
                        Qt.Key.Key_I,
                        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
                    )
                else:
                    click("beautify-button")
                wait(field + ".value===" + json.dumps(expected), "beautify " + suffix)
                assert path.read_text() == source
                QTest.keyClick(
                    window.view.focusProxy() or window.view,
                    Qt.Key.Key_Z,
                    Qt.KeyboardModifier.ControlModifier,
                )
                wait(
                    field + ".value===" + json.dumps(source),
                    "formatting is one undo step " + suffix,
                )
                click("beautify-button")
                wait(field + ".value===" + json.dumps(expected), "format again " + suffix)
                click("save-button")
                wait(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "save formatted " + suffix,
                )
                assert path.read_text() == expected
                edit(invalid)
                click("beautify-button")
                wait(
                    "!document.getElementById('beautify-button').disabled && document.getElementById('toast').textContent.startsWith('Could not format')",
                    "invalid source reports an error " + suffix,
                )
                assert evaluate(field + ".value") == invalid and path.read_text() == expected
                edit(expected)

            def slow_format(source, fmt):
                time.sleep(0.3)
                return beautify_source(source, fmt)

            with patch("reader.source_formatting.beautify_source", side_effect=slow_format):
                edit("<r><child/></r>")
                click("beautify-button")
                edit("<r>Changed while formatting</r>")
                wait(
                    "document.getElementById('toast').textContent.startsWith('The source changed')",
                    "a pending formatter never overwrites newer edits",
                )
                assert evaluate(field + ".value") == "<r>Changed while formatting</r>"
            assert not errors, errors
            print("Source formatting smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
