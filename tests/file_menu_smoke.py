"""Exercise actual right clicks, native file actions, ordering and window transfers."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Synthetic clicks do not carry the compositor serial required by the Wayland clipboard.
# Keep a real WebEngine page, with Qt's offscreen clipboard for this integration check.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu"
    ).strip()
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication, QMessageBox

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-file-menu-") as temporary:
        folder = Path(temporary)
        paths = [folder / name for name in ("اول با فاصله.md", "second.md", "third.md")]
        for path in paths:
            path.write_text(f"# {path.stem}\n\nOriginal text.")
        window = ReaderWindow(paths, settings_path=folder / "settings.ini")
        window.resize(1320, 900)
        window.show()
        manager = window.manager

        def evaluate(script, target=None):
            values = []
            (target or window).page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(script, target=None):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script, target):
                    return
                QTest.qWait(40)
            raise AssertionError(f"{script}: {errors}")

        def native_wait(condition):
            deadline = time.monotonic() + 15
            while not condition() and time.monotonic() < deadline:
                QTest.qWait(40)
            assert condition()

        def row(path, library=False):
            return (
                f'.library-item[data-path="{path}"] .library-open'
                if library
                else f'.file-item[data-id="{path}"] .file-select'
            )

        def open_menu(selector, keyboard=False):
            evaluate(f"document.querySelector({json.dumps(selector)}).scrollIntoView()")
            QTest.qWait(80)
            if keyboard:
                evaluate(f"document.querySelector({json.dumps(selector)}).focus()")
                QTest.keyClick(
                    window.view.focusProxy() or window.view,
                    Qt.Key.Key_F10,
                    Qt.KeyboardModifier.ShiftModifier,
                )
            else:
                x, y = json.loads(
                    evaluate(
                        "JSON.stringify((()=>{const r=document.querySelector("
                        + json.dumps(selector)
                        + ").getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())"
                    )
                )
                point = window.view.mapTo(window, QPoint(round(x), round(y)))
                QTest.mouseClick(window.windowHandle(), Qt.MouseButton.RightButton, pos=point)
            wait("!document.getElementById('file-context-menu').hidden")
            QTest.qWait(120)

        def action(name):
            selector = f'#file-context-menu [data-action="{name}"]'
            assert not evaluate(f"document.querySelector({json.dumps(selector)}).disabled"), name
            evaluate(f"document.querySelector({json.dumps(selector)}).click()")
            QTest.qWait(100)

        def order(library=False):
            selector = ".library-item" if library else ".file-item"
            key = "path" if library else "id"
            return json.loads(
                evaluate(
                    f"JSON.stringify([...document.querySelectorAll('{selector}')].map(e=>e.dataset.{key}))"
                )
            )

        try:
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===3 && document.querySelectorAll('.library-item').length===3"
            )
            first, second, third = map(str, paths)
            open_menu(row(first))
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "file-menu-light.png"))
            action("copy-path")
            assert app.clipboard().text() == first
            open_menu(row(first))
            action("copy-name")
            assert app.clipboard().text() == paths[0].name
            open_menu(row(first, True))
            action("copy")
            mime = app.clipboard().mimeData()
            assert [url.toLocalFile() for url in mime.urls()] == [first]
            assert bytes(mime.data("x-special/gnome-copied-files")).startswith(b"copy\nfile:///")
            assert bytes(mime.data("application/x-kde-cutselection")) == b"0"
            open_menu(row(first))
            action("cut")
            mime = app.clipboard().mimeData()
            assert [url.toLocalFile() for url in mime.urls()] == [first]
            assert bytes(mime.data("x-special/gnome-copied-files")).startswith(b"cut\nfile:///")
            assert bytes(mime.data("application/x-kde-cutselection")) == b"1"
            assert paths[0].is_file(), "Cut must leave the source until it is pasted"
            with patch("reader.ui.bridge.QDesktopServices.openUrl", return_value=True) as opened:
                open_menu(row(first))
                action("open-folder")
                assert opened.call_args.args[0].toLocalFile() == str(folder)
            print(
                "PASS: real right clicks, copy/cut file URLs, Unicode path and containing folder",
                flush=True,
            )

            open_menu(row(first), keyboard=True)
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_End)
            assert evaluate("document.activeElement.dataset.action==='close'")
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Escape)
            assert evaluate("document.getElementById('file-context-menu').hidden")
            assert evaluate(
                f"document.activeElement===document.querySelector({json.dumps(row(first))})"
            )
            print("PASS: keyboard menu navigation and Escape restore focus", flush=True)

            evaluate("document.getElementById('theme-button').click()")
            window.resize(860, 600)
            QTest.qWait(150)
            open_menu(row(first))
            assert evaluate(
                "(()=>{const r=document.getElementById('file-context-menu').getBoundingClientRect();return r.left>=0 && r.top>=0 && r.right<=innerWidth && r.bottom<=innerHeight})()"
            )
            window.grab().save(str(ROOT / "artifacts" / "file-menu-dark.png"))
            evaluate("document.getElementById('sidebar-collapse').click()")
            assert evaluate("document.getElementById('file-context-menu').hidden")
            QTest.qWait(150)
            window.grab().save(str(ROOT / "artifacts" / "sidebar-minimized.png"))
            evaluate("document.getElementById('sidebar-collapse').click()")
            evaluate("document.getElementById('theme-button').click()")
            window.resize(1320, 900)
            QTest.qWait(150)

            open_menu(row(third, True))
            action("star")
            native_wait(lambda: window.bridge.library.get(third)["starred"])
            open_menu(row(third))
            action("pin")
            native_wait(lambda: window.bridge.library.get(third)["pinned"])
            assert order()[0] == order(True)[0] == third
            open_menu(row(first))
            action("pin")
            open_menu(row(third))
            action("move-up")
            assert order()[0] == order(True)[0] == third
            open_menu(row(third, True))
            action("move-down")
            assert order()[:2] == order(True)[:2] == [first, third]
            for path in (first, second):
                open_menu(row(path, True))
                action("star")
            open_menu(row(third))
            action("pin")
            open_menu(row(first))
            action("pin")
            open_menu(row(third, True))
            action("star")
            evaluate("document.getElementById('library-starred').click()")
            assert order(True) == [first, second]
            open_menu(row(first, True))
            action("move-down")
            assert order(True) == [second, first]
            evaluate("document.getElementById('library-all').click()")
            expected = order()
            assert expected == order(True)
            print("PASS: stars, pin groups and relative order agree in both lists", flush=True)

            open_menu(row(first))
            action("open")
            evaluate("document.getElementById('edit-mode').click()")
            modified = "# Edited from menu\n\nUnsaved changes stay with the document."
            evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])');e.value="
                + json.dumps(modified)
                + ";e.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )
            open_menu(row(first))
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                action("close")
            assert first in order()
            open_menu(row(first))
            action("save")
            native_wait(lambda: paths[0].read_text() == modified)
            evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])');e.value+=' More edits';e.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )
            open_menu(row(first))
            action("new-window")
            native_wait(lambda: len(manager.windows) == 2 and not manager.transfers)
            destination = next(item for item in manager.windows if item is not window)
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===1",
                destination,
            )
            assert (
                next(iter(destination.bridge.sessions.values())).document.source
                == modified + " More edits"
            )
            assert first not in order()
            assert paths[0].read_text() == modified
            print(
                "PASS: close cancellation, save and new-window transfer preserve edits", flush=True
            )

            open_menu(row(second))
            action("close")
            native_wait(lambda: second not in window.bridge.sessions)
            open_menu(row(second, True))
            action("new-window")
            native_wait(lambda: len(manager.windows) == 3)
            last = manager.windows[-1]
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===1",
                last,
            )
            assert next(iter(last.bridge.sessions.values())).document.path == second
            assert [record["path"] for record in last.bridge.library.entries()] == expected
            print(
                "PASS: closed library files open in a fresh window with persisted order", flush=True
            )
            open_menu(row(first, True))
            action("new-window")
            native_wait(lambda: not manager.transfers and destination not in manager.windows)
            assert len(manager.windows) == 3
            owner = manager.path_owner(first)
            assert owner is not destination
            assert (
                next(iter(owner.bridge.sessions.values())).document.source
                == modified + " More edits"
            )
            print(
                "PASS: library new-window action preserves another window's unsaved buffer",
                flush=True,
            )

            evaluate("document.getElementById('new-file').click()")
            wait("document.getElementById('current-filename').title==='Not saved to disk'")
            draft = evaluate("readerApp.activeId")
            open_menu(f'.file-item[data-id="{draft}"] .file-select')
            assert evaluate(
                "['copy','cut','copy-path','open-folder','star','pin'].every(id=>document.querySelector('#file-context-menu [data-action='+id+']').disabled)"
            )
            action("close")
            # A missing file still permits copying its old path or forgetting its metadata.
            open_menu(row(third))
            action("close")
            paths[2].unlink()
            window.bridge.publish_library()
            QTest.qWait(100)
            open_menu(row(third, True))
            assert evaluate(
                "['open','new-window','copy','cut'].every(id=>document.querySelector('#file-context-menu [data-action='+id+']').disabled)"
            )
            action("copy-path")
            assert app.clipboard().text() == third
            open_menu(row(third, True))
            action("forget")
            native_wait(lambda: window.bridge.library.get(third) is None)
            assert not errors, errors
            print("PASS: unsaved and missing files have appropriate available actions", flush=True)
            print("File menu smoke test passed.", flush=True)
        finally:
            app.clipboard().clear()
            for item in list(manager.windows):
                item.allow_close = True
                item.close()
                item.page.deleteLater()
                QTest.qWait(100)
                item.deleteLater()
                QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
