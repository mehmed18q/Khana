"""Exercise the sidebar's real pointer/keyboard controls, persistence and themes."""

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
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    app.setQuitOnLastWindowClosed(False)
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-sidebar-") as temporary:
        folder = Path(temporary)
        settings = folder / "settings.ini"
        paths = [folder / f"Reading {i}.md" for i in range(8)]
        for path in paths:
            path.write_text(
                "\n\n".join(f"## Section {i}\n\nمتن فارسی و English." for i in range(30))
            )
        window = None

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

        def height(identifier):
            return evaluate(
                f"document.getElementById({json.dumps(identifier)}).getBoundingClientRect().height"
            )

        def point(selector):
            x, y = json.loads(
                evaluate(
                    "JSON.stringify((()=>{const r=document.querySelector("
                    + json.dumps(selector)
                    + ").getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())"
                )
            )
            return window.view.mapTo(window, QPoint(round(x), round(y)))

        def launch():
            nonlocal window
            window = ReaderWindow(paths, settings_path=settings)
            window.resize(1320, 900)
            window.show()
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===8 && document.fonts.status==='loaded'",
                "sidebar loaded",
            )
            QTest.qWait(150)

        def close():
            nonlocal window
            window.allow_close = True
            window.close()
            QTest.qWait(100)
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
            window = None

        try:
            launch()
            original = height("library-content")
            evaluate(
                "window.savedTab=document.querySelector('.file-item');document.getElementById('file-list').scrollTop=60"
            )
            click("files-toggle")
            assert evaluate(
                "document.getElementById('files-content').hidden && document.getElementById('files-toggle').getAttribute('aria-expanded')==='false'"
            )
            assert height("library-content") > original + 30
            click("files-toggle")
            assert evaluate(
                "document.querySelector('.file-item')===window.savedTab && document.getElementById('file-list').scrollTop>50"
            )
            print("PASS: collapse redistributes space and retains the file list", flush=True)

            selector = "[data-sidebar-section=files] .sidebar-resizer"
            start = point(selector)
            before = height("files-content")
            handle = window.windowHandle()
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(handle, start + QPoint(0, 40))
            QTest.qWait(100)
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start + QPoint(0, 40))
            assert abs(height("files-content") - before - 40) < 3
            print("PASS: pointer drag adjusts section heights", flush=True)
            evaluate("document.querySelector(" + json.dumps(selector) + ").focus()")
            before = height("files-content")
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Up)
            QTest.qWait(100)
            assert abs(height("files-content") - before + 16) < 3
            start = point(selector)
            before = height("files-content")
            QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(handle, start + QPoint(0, 25))
            QTest.qWait(80)
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Escape)
            QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start + QPoint(0, 25))
            assert abs(height("files-content") - before) < 2
            print("PASS: keyboard sizing and Escape cancellation", flush=True)

            click("library-toggle")
            assert evaluate(
                "document.querySelector('[data-sidebar-section=files] .sidebar-resizer').getAttribute('aria-controls')==='files-content outline-content'"
            )
            click("files-toggle")
            click("outline-toggle")
            assert evaluate(
                "[...document.querySelectorAll('.sidebar-section-content,.sidebar-resizer')].every(node=>node.hidden)"
            )
            click("files-toggle")
            click("outline-toggle")
            window.resize(980, 600)
            QTest.qWait(200)
            assert evaluate(
                "[...document.querySelectorAll('.sidebar-toggle')].every(node=>node.getBoundingClientRect().bottom<innerHeight)"
            )
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            window.resize(1320, 900)
            QTest.qWait(200)
            print("PASS: collapsed sections and short windows remain usable", flush=True)

            click("theme-button")
            assert evaluate("getComputedStyle(document.documentElement).colorScheme==='dark'")
            assert evaluate(
                "(()=>{const s=getComputedStyle(document.getElementById('new-format')),o=getComputedStyle(document.querySelector('#new-format option'));return s.backgroundColor==='rgb(33, 44, 38)' && o.backgroundColor===s.backgroundColor && o.color===s.color})()"
            )
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "sidebar-dark.png"))
            # Open the actual native select popup and navigate it with the keyboard.
            QTest.mouseClick(handle, Qt.MouseButton.LeftButton, pos=point("#new-format"))
            QTest.qWait(150)
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Down)
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Return)
            QTest.qWait(100)
            assert evaluate("document.getElementById('new-format').value==='HTML'")
            print("PASS: dark format menu has matching colors and remains functional", flush=True)
            saved = json.loads(evaluate("JSON.stringify(readerApp.settings.sidebar)"))
            QTest.qWait(100)
            window.bridge.settings.sync()
            assert json.loads(window.bridge.settings.value("reading"))["sidebar"] == saved
            close()
            launch()
            assert json.loads(evaluate("JSON.stringify(readerApp.settings.sidebar)")) == saved
            assert evaluate(
                "document.getElementById('library-content').hidden && document.body.dataset.theme==='dark'"
            )
            click("library-toggle")
            click("theme-button")
            assert evaluate(
                "getComputedStyle(document.documentElement).colorScheme==='light' && getComputedStyle(document.querySelector('#new-format option')).backgroundColor==='rgb(255, 255, 255)'"
            )
            print(
                "PASS: proportions and collapsed sections survive restart; light colors restore",
                flush=True,
            )
            assert not errors, errors
            print("Sidebar smoke test passed.", flush=True)
        finally:
            if window is not None:
                close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
