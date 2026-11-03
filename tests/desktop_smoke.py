"""Real Qt/WebEngine integration check. Run on a desktop: python tests/desktop_smoke.py."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader import VERSION
from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    console_errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            console_errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-test-") as folder:
        window = ReaderWindow(settings_path=Path(folder) / "settings.ini")
        window.showFullScreen()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda value: values.append(value))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, f"JavaScript timed out: {script[:100]}"
            return values[0]

        def wait_for(script, message):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", message, flush=True)
                    return
                QTest.qWait(80)
            details = evaluate(
                "JSON.stringify({active:window.readerApp?.activeId,fonts:document.fonts.status,visibility:document.visibilityState,toast:document.getElementById('toast')?.textContent})"
            )
            raise AssertionError(
                f"{message}; console: {console_errors}; {details}; initialized: {window.bridge.initialized}; loads: {list(window.bridge.jobs.loads)}; sessions: {list(window.bridge.sessions)}"
            )

        try:
            wait_for(
                "!!window.readerApp?.activeId && document.fonts.status === 'loaded'",
                "desktop bridge, fonts and sample load",
            )
            assert evaluate("document.getElementById('app-version').textContent") == f"/ {VERSION}"
            assert window.isFullScreen()
            print("PASS: starts fullscreen", flush=True)

            def point(selector):
                x, y = json.loads(
                    evaluate(
                        "JSON.stringify((()=>{const r=document.querySelector("
                        + json.dumps(selector)
                        + ").getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())"
                    )
                )
                return window.view.mapTo(window, QPoint(round(x), round(y)))

            def wait_for_move(count):
                deadline = time.monotonic() + 5
                while move.call_count < count and time.monotonic() < deadline:
                    QTest.qWait(20)
                assert move.call_count == count

            handle = window.windowHandle()
            with patch.object(handle, "startSystemMove", return_value=True) as move:
                # Send real Qt input through WebEngine and WebChannel, keeping
                # the native mouse button held until the bridge receives it.
                title = point("#current-filename")
                QTest.mouseClick(handle, Qt.MouseButton.LeftButton, pos=title)
                QTest.qWait(120)
                assert window.isFullScreen() and not move.called
                QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=title)
                QTest.mouseMove(handle, title + QPoint(2, 1))
                QTest.qWait(120)
                assert window.isFullScreen() and not move.called
                QTest.mouseMove(handle, title + QPoint(35, 12))
                wait_for_move(1)
                QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=title + QPoint(35, 12))
                assert move.call_count == 1 and not window.isFullScreen()
                print(
                    "PASS: header drag restores fullscreen and requests a native move", flush=True
                )

                QTest.qWait(200)
                for selector in (".brand-name", ".topbar"):
                    start = point(selector)
                    before = move.call_count
                    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
                    QTest.mouseMove(handle, start + QPoint(30, 15))
                    wait_for_move(before + 1)
                    QTest.mouseRelease(
                        handle, Qt.MouseButton.LeftButton, pos=start + QPoint(30, 15)
                    )
                    assert move.call_count == before + 1
                print("PASS: windowed header and logo request native movement", flush=True)

                before = move.call_count
                start = point("#search-button svg")
                QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(handle, start + QPoint(-50, 0))
                QTest.qWait(120)
                QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start + QPoint(-50, 0))
                assert move.call_count == before
                QTest.mouseClick(handle, Qt.MouseButton.LeftButton, pos=point("#search-button"))
                wait_for(
                    "!document.getElementById('search-panel').hidden",
                    "header buttons still receive clicks",
                )
                evaluate("document.getElementById('search-close').click()")

                start = point("#current-filename")
                QTest.mousePress(handle, Qt.MouseButton.RightButton, pos=start)
                QTest.mouseMove(handle, start + QPoint(40, 0))
                QTest.qWait(100)
                QTest.mouseRelease(handle, Qt.MouseButton.RightButton, pos=start + QPoint(40, 0))
                window.bridge.startWindowMove()  # Released pointer / delayed bridge call.
                assert move.call_count == before
                evaluate(
                    "document.querySelector('.topbar').dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}))"
                )
                QTest.qWait(150)
                assert window.isFullScreen()
                evaluate(
                    "document.querySelector('#theme-button svg').dispatchEvent(new MouseEvent('dblclick',{bubbles:true,button:0}))"
                )
                QTest.qWait(100)
                assert window.isFullScreen()
                print(
                    "PASS: double-click toggles fullscreen; controls and released/right pointers never move",
                    flush=True,
                )

            wait_for(
                "document.documentElement.lang === 'en' && document.getElementById('open-file').textContent.includes('Open file')",
                "English UI",
            )
            wait_for(
                "[...document.querySelectorAll('#document p')].find(p=>p.textContent.startsWith('Markdown')).dir === 'rtl'",
                "English-leading Persian paragraph stays RTL",
            )
            wait_for(
                "[...document.querySelectorAll('#document p')].find(p=>p.textContent.startsWith('This paragraph')).dir === 'ltr'",
                "English paragraph stays LTR",
            )
            wait_for(
                "getComputedStyle(document.querySelector('#document pre')).direction === 'ltr'",
                "code is LTR",
            )
            assert evaluate(
                "getComputedStyle(document.querySelector('#document p code')).whiteSpace === 'pre'"
            )
            artifact = ROOT / "artifacts"
            artifact.mkdir(exist_ok=True)
            QTest.qWait(250)
            assert evaluate(
                "document.getElementById('outline').scrollWidth <= document.getElementById('outline').clientWidth"
            )
            window.grab().save(str(artifact / "desktop-light.png"))

            evaluate("document.querySelector('[data-direction=ltr]').click()")
            assert evaluate(
                "[...document.querySelectorAll('#document [data-block]')].every(e=>e.dir==='ltr')"
            )
            evaluate("document.querySelector('[data-direction=smart]').click()")
            evaluate("document.querySelector('#document p .block-direction').click()")
            evaluate("document.querySelector('#document p .block-direction').click()")
            assert evaluate("document.querySelector('#document p').dir==='ltr'")
            evaluate("document.querySelector('[data-direction=smart]').click()")
            print("PASS: global and per-block direction controls", flush=True)

            evaluate(
                "document.getElementById('search-button').click(); document.getElementById('search-input').value='اینجا خوانا'; readerApp.search()"
            )
            assert evaluate("document.getElementById('search-count').textContent==='1 of 1'")
            evaluate(
                "document.getElementById('search-input').value='Markdown'; readerApp.search(); document.getElementById('search-next').click()"
            )
            assert evaluate(
                "document.getElementById('search-count').textContent.startsWith('2 of')"
            )
            evaluate("document.getElementById('search-close').click()")
            print("PASS: search across formatted text and match navigation", flush=True)

            evaluate(
                "document.getElementById('theme-button').click(); document.getElementById('font-size').value=20; document.getElementById('font-size').dispatchEvent(new Event('input'))"
            )
            wait_for(
                "document.body.dataset.theme==='dark' && getComputedStyle(document.getElementById('document')).fontSize==='20px'",
                "theme and typography",
            )
            QTest.qWait(250)
            window.grab().save(str(artifact / "desktop-dark.png"))
            evaluate(
                "document.getElementById('theme-button').click(); document.getElementById('reset-appearance').click(); document.getElementById('focus-button').click()"
            )
            wait_for("document.body.classList.contains('focus-mode')", "reading fullscreen enters")
            evaluate("document.getElementById('focus-button').click()")
            wait_for("!document.body.classList.contains('focus-mode')", "reading fullscreen exits")
            window.toggle_fullscreen()
            assert not window.isFullScreen()
            window.resize(1000, 740)
            QTest.qWait(150)
            assert evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            print("PASS: focus, fullscreen toggle and narrow window", flush=True)

            fixture = Path(folder) / "mixed.html"
            fixture.write_text(
                (ROOT / "examples" / "mixed-content.html").read_text(), encoding="utf-8"
            )
            with patch(
                "reader.ui.bridge.QFileDialog.getOpenFileNames", return_value=([str(fixture)], "")
            ):
                window.bridge.openFiles()
            wait_for(
                "window.readerApp.activeId.endsWith('mixed.html')",
                "native file selection opens HTML",
            )
            assert evaluate("document.getElementById('document-format').textContent==='HTML'")
            assert evaluate(
                "[...document.querySelectorAll('#document bdi[dir=ltr]')].some(e=>e.textContent==='Visual Studio Code')"
            )
            evaluate("document.querySelector('#document a').click()")
            QTest.qWait(150)
            assert evaluate("document.getElementById('doc-heading-intro') !== null")
            print("PASS: HTML formatting, anchors and English runs across bold markup", flush=True)

            fixture.write_text(
                "<h1>Updated HTML</h1><p>تغییر از دیسک</p><script>window.PWNED=true</script>",
                encoding="utf-8",
            )
            window.bridge.reloadFile(str(fixture))
            wait_for(
                "document.querySelector('#document h1')?.textContent==='Updated HTML'",
                "reload reads updated file from disk",
            )
            assert evaluate(
                "window.PWNED === undefined && !document.querySelector('#document script')"
            )

            dropped = Path(folder) / "dropped.md"
            dropped.write_text("# Dropped document\n\nمتن فارسی", encoding="utf-8")
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(dropped))])
            enter = QDragEnterEvent(
                window.view.rect().center(),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.view.dragEnterEvent(enter)
            assert enter.isAccepted()
            drop = QDropEvent(
                QPointF(window.view.rect().center()),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.view.dropEvent(drop)
            wait_for("window.readerApp.activeId.endsWith('dropped.md')", "native drag and drop")
            window.bridge.load_paths([Path(folder) / "missing.md"])
            wait_for(
                "document.getElementById('toast').textContent.includes('File not found')",
                "file error is visible without losing current document",
            )
            assert evaluate("window.readerApp.activeId.endsWith('dropped.md')")
            while evaluate("window.readerApp.activeId !== null"):
                evaluate("readerApp.closeDocument(readerApp.activeId)")
            assert evaluate("!document.getElementById('empty-state').hidden")
            print("PASS: close files and empty state", flush=True)
            assert not console_errors, console_errors
            print("PASS: no JavaScript errors", flush=True)
            print("Desktop smoke test passed.", flush=True)
        finally:
            window.close()
            QTest.qWait(100)
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
