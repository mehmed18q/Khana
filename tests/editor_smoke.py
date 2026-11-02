"""Exercise editing and save/discard/cancel through the real Qt WebChannel."""

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
from PySide6.QtWidgets import QApplication, QMessageBox

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    console_errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            console_errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-edit-test-") as folder:
        base = Path(folder)
        window = ReaderWindow(settings_path=base / "settings.ini")
        window.showFullScreen()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda value: values.append(value))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, f"JavaScript timeout: {script[:100]}"
            return values[0]

        def wait_for(script, label):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            raise AssertionError(f"{label}; console: {console_errors}")

        def edit(source):
            evaluate(
                "(() => { const e = document.querySelector('.source-editor:not([hidden])'); e.value = "
                + json.dumps(source)
                + "; e.dispatchEvent(new Event('input', {bubbles:true})); })()"
            )

        def click(name):
            evaluate(f"document.getElementById('{name}').click()")

        def current_source():
            return evaluate("document.querySelector('.source-editor:not([hidden])')?.value")

        def current_id():
            return evaluate("readerApp.activeId")

        def select(start, end):
            evaluate(
                f"(() => {{ const e = document.querySelector('.source-editor:not([hidden])'); e.focus(); e.setSelectionRange({start}, {end}); }})()"
            )

        def shortcut(key, modifiers=Qt.KeyboardModifier.ControlModifier):
            QTest.keyClick(window.view.focusProxy() or window.view, key, modifiers)
            QTest.qWait(100)

        try:
            wait_for("!!window.readerApp?.activeId", "editor shell loads")
            sample_id = current_id()
            click("new-file")
            wait_for(
                "readerApp.activeId.startsWith('untitled:') && document.body.classList.contains('editing')",
                "New opens an editable Markdown document",
            )
            first_id = current_id()
            shortcut(Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier)
            assert not window.isFullScreen()
            shortcut(Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier)
            assert window.isFullScreen()
            print("PASS: F11 works with the source editor focused", flush=True)
            source = '# یادداشت تازه\n\nMarkdown برای نوشتن متن فارسی و انگلیسی مناسب است.\n\n```python\nprint("سلام")\n```\n'
            edit(source)
            wait_for(
                "document.querySelector('#document h1')?.textContent === 'یادداشت تازه'",
                "live preview renders Persian Markdown",
            )
            assert evaluate(
                "document.getElementById('save-status').textContent === 'Unsaved changes'"
            )
            assert evaluate("document.querySelector('#document p').dir === 'rtl'")
            assert evaluate(
                "getComputedStyle(document.querySelector('#document pre')).direction === 'ltr'"
            )
            edit("سلام English")
            select(5, 12)
            shortcut(Qt.Key.Key_B)
            assert current_source() == "سلام **English**"
            wait_for(
                "document.querySelector('#document strong')?.textContent === 'English'",
                "Ctrl+B formats selected text in the live preview",
            )
            shortcut(Qt.Key.Key_Z)
            assert current_source() == "سلام English"
            print("PASS: toolbar formatting is undoable", flush=True)
            select(5, 12)
            shortcut(Qt.Key.Key_I)
            assert current_source() == "سلام *English*"
            shortcut(Qt.Key.Key_I)
            assert current_source() == "سلام English"
            select(5, 12)
            shortcut(
                Qt.Key.Key_X,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            assert current_source() == "سلام ~~English~~"
            print("PASS: Ctrl+I toggles italic and Ctrl+Shift+X applies strikethrough", flush=True)
            edit("code")
            select(0, 4)
            shortcut(Qt.Key.Key_QuoteLeft)
            assert current_source() == "`code`"
            edit("Heading")
            select(0, 7)
            evaluate("document.querySelector('[data-format=h2]').click()")
            assert current_source() == "## Heading"
            edit("اول\nSecond")
            select(0, 10)
            evaluate("document.querySelector('[data-format=bullet]').click()")
            wait_for(
                "document.querySelectorAll('#document li').length===2",
                "toolbar formats selected lines as a list",
            )
            edit("link text")
            select(0, 9)
            shortcut(Qt.Key.Key_K)
            assert evaluate("document.getElementById('link-dialog').open"), (
                console_errors,
                current_source(),
                evaluate("document.activeElement?.outerHTML"),
            )
            click("link-cancel")
            QTest.qWait(80)
            assert current_source() == "link text"
            select(0, 9)
            shortcut(Qt.Key.Key_K)
            evaluate(
                "document.getElementById('link-url').value='javascript:alert(1)'; document.getElementById('link-form').requestSubmit()"
            )
            assert evaluate(
                "!document.getElementById('link-error').hidden && document.getElementById('link-dialog').open"
            )
            assert current_source() == "link text"
            evaluate(
                "document.getElementById('link-url').value='https://example.com/a(b)'; document.getElementById('link-form').requestSubmit()"
            )
            assert current_source() == "[link text](<https://example.com/a(b)>)"
            wait_for(
                "document.querySelector('#document a')?.getAttribute('href')==='https://example.com/a(b)'",
                "Ctrl+K inserts a validated link and preserves the selection",
            )
            edit("")
            select(0, 0)
            evaluate("document.querySelector('[data-format=bold]').click()")
            assert current_source() == "**bold text**"
            assert evaluate(
                "(() => { const e=document.querySelector('.source-editor:not([hidden])'); return e.value.slice(e.selectionStart,e.selectionEnd)==='bold text'; })()"
            )
            print("PASS: formatting at the caret inserts a selected placeholder", flush=True)
            edit(source)
            wait_for(
                "document.querySelector('#document h1')?.textContent === 'یادداشت تازه'",
                "preview returns to the edited source",
            )
            evaluate(
                "(() => { const e = document.querySelector('.source-editor:not([hidden])'); e.focus(); e.setSelectionRange(e.value.length, e.value.length); })()"
            )
            QTest.keyClicks(window.view.focusProxy() or window.view, "X")
            wait_for(
                "document.querySelector('.source-editor:not([hidden])').value.endsWith('X')",
                "native source typing",
            )
            evaluate("readerApp.showDocument(" + json.dumps(sample_id) + ")")
            evaluate("readerApp.showDocument(" + json.dumps(first_id) + ")")
            evaluate("document.querySelector('.source-editor:not([hidden])').focus()")
            QTest.keyClick(
                window.view.focusProxy() or window.view,
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier,
            )
            QTest.qWait(100)
            assert current_source() == source, repr(current_source())
            QTest.keyClick(
                window.view.focusProxy() or window.view,
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            QTest.qWait(100)
            assert current_source() == source + "X"
            QTest.keyClick(
                window.view.focusProxy() or window.view,
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier,
            )
            QTest.qWait(100)
            assert current_source() == source
            print("PASS: native undo/redo survives tab switching", flush=True)
            window.bridge.previewReady.emit(
                json.dumps(
                    {
                        "id": first_id,
                        "revision": 0,
                        "html": "<h1>Stale preview</h1>",
                        "headings": [],
                        "words": 2,
                    }
                )
            )
            QTest.qWait(100)
            assert evaluate(
                "!document.getElementById('document').textContent.includes('Stale preview')"
            )
            QTest.qWait(150)
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            window.grab().save(str(artifacts / "editor-light.png"))

            # Typing followed immediately by save must save the latest text,
            # even when the debounced preview has not run yet.
            first = base / "first.md"
            source += "\nLatest keystroke\n"
            edit(source)
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(first.with_suffix("")), "Markdown (*.md)"),
            ):
                click("save-button")
                wait_for(
                    "document.getElementById('current-filename').textContent === 'first.md' && document.getElementById('save-status').textContent === 'Saved'",
                    "Save opens a dialog and adds the default extension",
                )
            assert first.read_text() == source
            assert current_id() == first_id

            source += "Saved with Ctrl+S\n"
            edit(source)
            with patch("reader.ui.bridge.QFileDialog.getSaveFileName") as dialog:
                QTest.keyClick(
                    window.view.focusProxy() or window.view,
                    Qt.Key.Key_S,
                    Qt.KeyboardModifier.ControlModifier,
                )
                QTest.qWait(100)
                wait_for(
                    "document.getElementById('save-status').textContent === 'Saved'",
                    "Ctrl+S saves an existing file without a dialog",
                )
                dialog.assert_not_called()
            assert first.read_text() == source

            copy = base / "copy.md"
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(copy), "Markdown (*.md)"),
            ):
                shortcut(
                    Qt.Key.Key_S,
                    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
                )
                wait_for(
                    "document.getElementById('current-filename').textContent === 'copy.md'",
                    "Save As changes the active filename",
                )
            edit(source + "Only in the copy\n")
            click("save-button")
            wait_for(
                "document.getElementById('save-status').textContent === 'Saved'",
                "subsequent Save targets the new file",
            )
            assert first.read_text() == source
            assert copy.read_text().endswith("Only in the copy\n")
            window.bridge.load_paths([first])
            wait_for(
                "document.getElementById('current-filename').textContent === 'first.md'",
                "original file can be reopened after Save As",
            )
            reopened_id = current_id()
            assert reopened_id != first_id
            evaluate("readerApp.showDocument(" + json.dumps(first_id) + ")")
            assert evaluate("document.getElementById('current-filename').textContent === 'copy.md'")
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(first), "Markdown (*.md)"),
            ):
                click("save-as-button")
                wait_for(
                    "document.getElementById('toast').textContent.includes('already open')",
                    "Save As protects files open in another tab",
                )
            assert first.read_text() == source

            # A canceled Save As must not rename the tab or clear the dirty flag.
            dirty = "# Unsaved revision\n\nتغییر ذخیره نشده\n"
            edit(dirty)
            with patch("reader.ui.bridge.QFileDialog.getSaveFileName", return_value=("", "")):
                click("save-as-button")
                QTest.qWait(150)
            assert current_source() == dirty
            assert evaluate(
                "document.getElementById('current-filename').textContent === 'copy.md' && document.getElementById('save-status').textContent === 'Unsaved changes'"
            )
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                evaluate("readerApp.closeDocument(readerApp.activeId)")
                QTest.qWait(150)
            assert current_id() == first_id and current_source() == dirty
            print("PASS: cancel Save As and cancel close preserve edits", flush=True)

            # Reopening an open file activates the draft, never replaces it.
            window.bridge.load_paths([copy])
            QTest.qWait(100)
            assert current_source() == dirty
            second_id = None
            click("new-file")
            wait_for(
                f"readerApp.activeId !== {json.dumps(first_id)}", "multiple independent drafts"
            )
            second_id = current_id()
            edit("# Second draft\n")
            evaluate("readerApp.showDocument(" + json.dumps(first_id) + ")")
            assert current_source() == dirty
            print("PASS: switching tabs and reopening files retain source buffers", flush=True)

            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                click("reload-button")
                QTest.qWait(150)
            assert current_source() == dirty
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Discard
            ):
                click("reload-button")
                wait_for(
                    "document.getElementById('save-status').textContent === 'Saved'",
                    "reload discards edits only after confirmation",
                )
            assert current_source() == copy.read_text()

            # A write failure keeps the dirty buffer and on-disk version intact.
            edit(dirty)
            original = copy.read_bytes()
            with patch(
                "reader.editing.EditSession.save", side_effect=PermissionError("Permission denied")
            ):
                click("save-button")
                wait_for(
                    "document.getElementById('toast').textContent.includes('Could not save')",
                    "save failure is visible",
                )
            assert copy.read_bytes() == original and current_source() == dirty
            assert evaluate(
                "document.getElementById('save-status').textContent === 'Unsaved changes'"
            )

            copy.write_text("External change", encoding="utf-8")
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                click("save-button")
                QTest.qWait(150)
            assert copy.read_text() == "External change" and current_source() == dirty
            with patch.object(window.bridge, "_ask", return_value=QMessageBox.StandardButton.Yes):
                click("save-button")
                wait_for(
                    "document.getElementById('save-status').textContent === 'Saved'",
                    "external changes require explicit replacement",
                )
            assert copy.read_text() == dirty

            # HTML source is saved verbatim; only the live preview is sanitized.
            evaluate("document.getElementById('new-format').value='HTML'")
            click("new-file")
            wait_for(
                "document.getElementById('document-format').textContent === 'HTML'",
                "New HTML document",
            )
            html_id = current_id()
            edit("سلام")
            select(0, 4)
            shortcut(Qt.Key.Key_B)
            assert current_source() == "<strong>سلام</strong>"
            shortcut(Qt.Key.Key_I)
            assert current_source() == "<strong><em>سلام</em></strong>"
            print("PASS: HTML formatting shortcuts insert HTML tags", flush=True)
            html = "<!doctype html><html><head><style>h1 { color: red }</style></head><body><h1>HTML فارسی</h1><script>window.unsafe = true</script></body></html>"
            edit(html)
            wait_for(
                "document.querySelector('#document h1')?.textContent === 'HTML فارسی'",
                "safe HTML live preview",
            )
            assert evaluate(
                "window.unsafe === undefined && !document.querySelector('#document script')"
            )
            html_path = base / "document.html"
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(html_path), "HTML (*.html *.htm)"),
            ):
                click("save-button")
                wait_for(
                    "document.getElementById('current-filename').textContent === 'document.html' && document.getElementById('save-status').textContent === 'Saved'",
                    "HTML Save preserves the original source",
                )
            assert html_path.read_text() == html

            # Save-on-close followed by canceling the filename dialog keeps a new draft.
            evaluate("readerApp.showDocument(" + json.dumps(second_id) + ")")
            with (
                patch.object(window.bridge, "_ask", return_value=QMessageBox.StandardButton.Save),
                patch("reader.ui.bridge.QFileDialog.getSaveFileName", return_value=("", "")),
            ):
                evaluate("readerApp.closeDocument(readerApp.activeId)")
                QTest.qWait(150)
            assert current_id() == second_id
            saved_on_close = base / "saved-on-close.md"
            with (
                patch.object(window.bridge, "_ask", return_value=QMessageBox.StandardButton.Save),
                patch(
                    "reader.ui.bridge.QFileDialog.getSaveFileName",
                    return_value=(str(saved_on_close), "Markdown (*.md)"),
                ),
            ):
                evaluate("readerApp.closeDocument(readerApp.activeId)")
                wait_for(
                    f"readerApp.activeId !== {json.dumps(second_id)}",
                    "Save on close writes the draft before closing it",
                )
            assert saved_on_close.read_text() == "# Second draft\n"

            # Check native window-close protection, including the most recent input.
            evaluate("readerApp.showDocument(" + json.dumps(html_id) + ")")
            edit(html + "\n<!-- unsaved -->")
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                window.close()
                QTest.qWait(200)
            assert window.isVisible() and not window.allow_close
            assert current_source().endswith("<!-- unsaved -->")
            print("PASS: native window close can be canceled without losing edits", flush=True)
            window.showNormal()
            window.resize(900, 720)
            QTest.qWait(150)
            assert evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert evaluate(
                "!document.getElementById('editor-pane').hidden && document.getElementById('reading-scroll').clientHeight > 100"
            )
            print("PASS: source and preview remain usable in a small window", flush=True)
            assert not console_errors, console_errors
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Discard
            ):
                window.close()
                QTest.qWait(200)
            assert not window.isVisible()
            assert html_path.read_text() == html
            print("PASS: discard on exit leaves saved files unchanged", flush=True)
            print("Editor smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(100)
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
