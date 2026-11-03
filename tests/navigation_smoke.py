"""Check reading fullscreen and Go to line through real Qt/WebEngine input."""

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt
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
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-navigation-") as temporary:
        folder = Path(temporary)
        path = folder / "navigation.md"
        source = "\n".join(
            f"## Line {i}\n\nفارسی و English {'wrapped text ' * 35}\n" for i in range(100)
        )
        path.write_text(source)
        window = ReaderWindow([path], settings_path=folder / "settings.ini")
        window.resize(1200, 800)
        window.show()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(40)
            raise AssertionError(f"{label}: {errors}")

        def click(identifier):
            evaluate(f"document.getElementById({json.dumps(identifier)}).click()")
            QTest.qWait(100)

        def key(value, modifiers=Qt.KeyboardModifier.NoModifier):
            QTest.keyClick(window.view.focusProxy() or window.view, value, modifiers)
            QTest.qWait(120)

        def line_dialog():
            key(Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
            assert evaluate("document.getElementById('go-to-line-dialog').open")

        def jump(value):
            line_dialog()
            evaluate(f"document.getElementById('go-to-line-input').value={json.dumps(str(value))}")
            key(Qt.Key.Key_Return)
            assert evaluate("!document.getElementById('go-to-line-dialog').open")

        def fullscreen(enabled):
            wait(
                f"document.body.classList.contains('focus-mode')==={str(enabled).lower()}",
                f"reading fullscreen {'enters' if enabled else 'exits'}",
            )
            assert window.focus_mode == enabled

        try:
            wait(
                "!!window.readerApp?.activeId && document.fonts.status==='loaded'",
                "document loaded",
            )
            assert evaluate(
                "[...document.querySelectorAll('#outline .outline-line')].every((n,i)=>n.textContent===`Ln ${i*4+1}`) && document.querySelectorAll('#outline .outline-line').length===100"
            )
            jump("۲۰۱")
            assert evaluate("!document.body.classList.contains('editing')")
            assert evaluate(
                "(()=>{const r=document.querySelector('#document [data-source-line=\"200\"]').getBoundingClientRect(),s=document.getElementById('reading-scroll').getBoundingClientRect();return r.top>=s.top && r.top<s.bottom})()"
            )
            assert evaluate("document.getElementById('reading-scroll').scrollTop>1000")
            wait(
                "!!document.querySelector('.reading-line-numbers [data-line=\"201\"]')",
                "reading gutter shows the destination source line",
            )
            assert evaluate(
                "Math.abs(document.querySelector('.reading-line-numbers [data-line=\"201\"]').getBoundingClientRect().top-document.querySelector('#document [data-source-line=\"200\"]').getBoundingClientRect().top)<2"
            )
            print("PASS: Ctrl+G accepts Persian digits and navigates in reading mode", flush=True)
            line_dialog()
            for invalid in ("0", "401", "2.5", "oops", ""):
                evaluate(f"document.getElementById('go-to-line-input').value={json.dumps(invalid)}")
                key(Qt.Key.Key_Return)
                assert evaluate(
                    "document.getElementById('go-to-line-dialog').open && !document.getElementById('go-to-line-error').hidden"
                )
            key(Qt.Key.Key_Escape)
            assert evaluate("!document.getElementById('go-to-line-dialog').open")
            assert evaluate("!document.body.classList.contains('editing')")
            click("edit-mode")
            # Navigation must scroll correctly even with preview sync disabled.
            click("sync-scroll")
            jump(301)
            expected = sum(len(line) + 1 for line in source.split("\n")[:300])
            assert (
                evaluate("document.querySelector('.source-editor:not([hidden])').selectionStart")
                == expected
            )
            assert evaluate(
                "document.getElementById('cursor-position').textContent==='Ln 301, Col 1'"
            )
            assert evaluate("document.querySelector('.source-editor:not([hidden])').scrollTop>2000")
            assert (
                evaluate("document.querySelector('.source-editor:not([hidden])').value") == source
            )
            assert evaluate("document.getElementById('save-status').textContent==='Saved'")
            wait(
                "document.querySelector('.editor-line-numbers .current-line')?.textContent==='301'",
                "editor gutter follows the caret and scroll position",
            )
            # The mirror accounts for the long wrapped lines before the destination.
            assert evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])'),m=document.querySelector('.source-mirror [data-line=\"300\"]');return m.offsetTop>=e.scrollTop && m.offsetTop<e.scrollTop+e.clientHeight})()"
            )
            click("cursor-position")
            assert evaluate("document.getElementById('go-to-line-input').value==='301'")
            key(Qt.Key.Key_Escape)
            assert evaluate("document.activeElement.classList.contains('source-editor')")
            jump(1)
            assert evaluate(
                "document.querySelector('.source-editor:not([hidden])').selectionStart===0"
            )
            evaluate("document.execCommand('insertText',false,'draft ')")
            jump(201)
            key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            assert (
                evaluate("document.querySelector('.source-editor:not([hidden])').value") == source
            )
            print(
                "PASS: editing navigation validates input, handles wrapping and preserves text",
                flush=True,
            )

            before = window.geometry()
            key(
                Qt.Key.Key_F,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            fullscreen(True)
            assert window.isFullScreen()
            assert evaluate("document.activeElement.classList.contains('source-editor')")
            assert evaluate(
                "[...document.querySelectorAll('.sidebar,.topbar,.document-toolbar,.reading-toolbar,.memory-toolbar,.preview-toolbar,.editor-heading,.format-toolbar,.editor-footer,.statusbar')].every(n=>!n.getClientRects().length)"
            )
            assert evaluate(
                "(()=>{const r=document.getElementById('document-workspace').getBoundingClientRect();return r.x===0 && r.y===0 && r.width===innerWidth && r.height===innerHeight})()"
            )
            line_dialog()
            key(Qt.Key.Key_Escape)
            assert window.focus_mode
            jump(101)
            assert evaluate(
                "document.getElementById('cursor-position').textContent==='Ln 101, Col 1'"
            )
            key(Qt.Key.Key_Escape)
            fullscreen(False)
            assert not window.isFullScreen()
            assert window.geometry() == before
            print(
                "PASS: fullscreen hides all chrome; dialogs and Go to line work inside it",
                flush=True,
            )

            window.showMaximized()
            QTest.qWait(200)
            click("focus-button")
            fullscreen(True)
            key(Qt.Key.Key_F11)
            fullscreen(False)
            assert window.isMaximized() and not window.isFullScreen()
            window.showFullScreen()
            QTest.qWait(200)
            click("focus-button")
            fullscreen(True)
            key(Qt.Key.Key_Escape)
            fullscreen(False)
            assert window.isFullScreen()
            print(
                "PASS: exiting restores maximized and native fullscreen window states", flush=True
            )

            click("read-mode")
            click("focus-button")
            fullscreen(True)
            jump(201)
            assert evaluate("!document.body.classList.contains('editing')")
            QTest.qWait(2900)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "reading-fullscreen.png"))
            # Hover and click the otherwise hidden exit control using real mouse input.
            QTest.mouseMove(window.windowHandle(), QPoint(window.width() // 2, 150))
            QTest.qWait(100)
            QTest.mouseMove(window.windowHandle(), QPoint(window.width() // 2, 12))
            QTest.qWait(300)
            assert evaluate(
                "getComputedStyle(document.getElementById('exit-focus-button')).opacity==='1'"
            )
            QTest.mouseClick(
                window.windowHandle(),
                Qt.MouseButton.LeftButton,
                pos=QPoint(window.width() // 2, 20),
            )
            fullscreen(False)
            click("focus-button")
            fullscreen(True)
            window.showNormal()
            fullscreen(False)
            assert evaluate("document.querySelector('.sidebar').getClientRects().length===1")
            log = folder / "large.log"
            log.write_text(
                "\n".join("" if i % 3 == 1 else f"Line {i} فارسی English" for i in range(12000))
                + "\n"
            )
            window.bridge.load_paths([log])
            wait("readerApp.activeId.endsWith('large.log')", "large source file opens")
            click("edit-mode")
            jump(11999)
            wait(
                "document.querySelector('.editor-line-numbers .current-line')?.textContent==='11999'",
                "large-file gutter retains exact line numbers between sampled anchors",
            )
            assert evaluate(
                "document.querySelectorAll('.editor-line-numbers > span').length<100 && document.querySelector('.source-mirror').children.length<=10001"
            )
            assert evaluate(
                "Math.abs(document.querySelector('.source-mirror').scrollHeight-document.querySelector('.source-editor:not([hidden])').scrollHeight)<3"
            )
            jump(12001)
            assert evaluate(
                "document.getElementById('cursor-position').textContent==='Ln 12001, Col 1'"
            )
            assert evaluate(
                "!!document.querySelector('.editor-line-numbers [data-line=\"12001\"]')"
            )
            key(Qt.Key.Key_Return)
            wait(
                "document.querySelector('.editor-line-numbers .current-line')?.textContent==='12002'",
                "trailing empty lines and newlines update the gutter",
            )
            key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "line-numbers.png"))
            assert path.read_text() == source
            assert not errors, errors
            print("Navigation smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(150)
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
