"""Real pointer selection/dragging, category dialogs, safe renaming and split actions."""

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
    with tempfile.TemporaryDirectory(prefix="khana-categories-") as temporary:
        folder = Path(temporary)
        paths = [
            folder / sub / name
            for sub, name in (("a", "سند اول.md"), ("b", "second.md"), ("c", "third.md"))
        ]
        for path in paths:
            path.parent.mkdir()
            path.write_text("# Original\n\nText to keep.")
        settings = folder / "settings.ini"
        window = None

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(script):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    return
                QTest.qWait(40)
            detail = evaluate(
                "JSON.stringify({title:document.getElementById('category-dialog-title').textContent,error:document.getElementById('category-error').textContent,disabled:document.getElementById('category-submit').disabled,name:document.getElementById('category-name').value,valid:document.getElementById('category-form').checkValidity()})"
            )
            raise AssertionError(
                f"{script}: {errors}; {detail}; {window.bridge.library.categories()}"
            )

        def native_wait(condition):
            deadline = time.monotonic() + 15
            while not condition() and time.monotonic() < deadline:
                QTest.qWait(40)
            assert condition()

        def click(identifier):
            evaluate(f"document.getElementById({json.dumps(identifier)}).click()")
            QTest.qWait(60)

        def section(scope, opened):
            if (
                evaluate(f"document.getElementById('{scope}-toggle').getAttribute('aria-expanded')")
                != str(opened).lower()
            ):
                click(scope + "-toggle")

        def launch():
            nonlocal window
            window = ReaderWindow(paths, settings_path=settings)
            window.resize(1320, 1000)
            window.show()
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===3"
            )
            QTest.qWait(200)

        def close():
            nonlocal window
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
            window = None

        def row(path, library=False):
            return (
                f'.library-item[data-path="{path}"] .library-open'
                if library
                else f'.file-item[data-id="{path}"] .file-select'
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

        def mouse(selector, control=False, right=False):
            evaluate(
                f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:'nearest',behavior:'instant'}})"
            )
            QTest.qWait(100)
            QTest.mouseClick(
                window.windowHandle(),
                Qt.MouseButton.RightButton if right else Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.ControlModifier if control else Qt.KeyboardModifier.NoModifier,
                point(selector),
            )
            QTest.qWait(100)

        def menu(selector):
            mouse(selector, right=True)
            wait("!document.getElementById('file-context-menu').hidden")

        def action(identifier):
            selector = '#file-context-menu [data-action="' + identifier + '"]'
            assert not evaluate(f"document.querySelector({json.dumps(selector)}).disabled"), (
                identifier
            )
            evaluate(f"document.querySelector({json.dumps(selector)}).click()")
            QTest.qWait(100)

        def submit_name(value):
            wait("document.getElementById('category-dialog').open")
            evaluate("document.getElementById('category-name').value=" + json.dumps(value))
            click("category-submit")
            wait("!document.getElementById('category-dialog').open")

        def category(name):
            return next(
                item["id"] for item in window.bridge.library.categories() if item["name"] == name
            )

        def drag(source, destination, cancel=False):
            start, end = point(source), point(destination)
            QTest.mousePress(window.windowHandle(), Qt.MouseButton.LeftButton, pos=start)
            QTest.qWait(60)
            QTest.mouseMove(window.windowHandle(), start + QPoint(12, 0))
            QTest.qWait(60)
            QTest.mouseMove(window.windowHandle(), end)
            wait("!!document.querySelector('.category-drop-target')")
            if cancel:
                QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_Escape)
            QTest.mouseRelease(window.windowHandle(), Qt.MouseButton.LeftButton, pos=end)
            QTest.qWait(200)

        try:
            launch()
            first, second, third = map(str, paths)
            section("library", False)
            section("outline", False)
            click("files-new-category")
            submit_name("مطالعه")
            a = category("مطالعه")
            click("library-new-category")
            submit_name("Work")
            b = category("Work")
            assert evaluate(
                "document.querySelectorAll('#file-list .file-category').length===3 && document.querySelectorAll('#library-list .file-category').length===3"
            )
            mouse(row(first))
            mouse(row(second), control=True)
            assert evaluate("document.querySelectorAll('#file-list .selected').length===2")
            menu(row(first))
            assert evaluate(
                "document.getElementById('file-context-menu').getAttribute('aria-label')==='Actions for 2 files'"
            )
            action("copy")
            assert {url.toLocalFile() for url in app.clipboard().mimeData().urls()} == {
                first,
                second,
            }
            menu(row(second))
            action("cut")
            assert bytes(app.clipboard().mimeData().data("application/x-kde-cutselection")) == b"1"
            assert all(path.is_file() for path in paths)
            menu(row(first))
            action("move-category")
            evaluate("document.getElementById('category-destination').value=" + json.dumps(a))
            click("category-submit")
            wait("!document.getElementById('category-dialog').open")
            assert window.bridge.library.get(first)["categoryId"] == a
            assert window.bridge.library.get(second)["categoryId"] == a
            assert evaluate(
                f"document.querySelector('#library-list [data-category-id=\"{a}\"]').querySelectorAll('.library-item').length===2"
            )
            print(
                "PASS: categories in both lists, Ctrl selection, multi-file copy/cut and destination picker",
                flush=True,
            )

            group_b = f'#file-list [data-category-id="{b}"] .category-toggle'
            menu(group_b)
            action("category-up")
            assert window.bridge.library.categories()[0]["id"] == b
            menu(group_b)
            action("category-rename")
            submit_name("پروژه <۱۴۰۵>")
            drag(row(first), group_b)
            native_wait(
                lambda: all(
                    window.bridge.library.get(p)["categoryId"] == b for p in (first, second)
                )
            )
            assert all(path.is_file() for path in paths)
            print(
                "PASS: category rename/order and real multi-file pointer drag preserve original paths",
                flush=True,
            )

            section("files", False)
            section("library", True)
            mouse(row(first, True))
            group_a = f'#library-list [data-category-id="{a}"] .category-toggle'
            drag(row(first, True), group_a, cancel=True)
            assert window.bridge.library.get(first)["categoryId"] == b
            drag(row(first, True), group_a)
            native_wait(lambda: window.bridge.library.get(first)["categoryId"] == a)
            print("PASS: Library dragging and Escape cancellation", flush=True)

            note = window.bridge.library.save_annotation(
                first, "", "note", "Keep", "Note", {"index": 0, "progress": 0}
            )
            window.bridge.publish_library()
            mouse(row(first, True))
            click("edit-mode")
            edited = "# Unsaved while renaming\n\nنباید از دست برود."
            evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])');e.value="
                + json.dumps(edited)
                + ";e.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )
            collision = paths[0].with_name("existing.md")
            collision.write_text("Keep this too")
            menu(row(first, True))
            action("rename")
            evaluate("document.getElementById('category-name').value='existing.md'")
            click("category-submit")
            wait("!document.getElementById('category-error').hidden")
            assert collision.read_text() == "Keep this too"
            assert paths[0].is_file()
            click("category-cancel")
            menu(row(first, True))
            action("rename")
            submit_name("نام جدید.md")
            renamed = paths[0].with_name("نام جدید.md")
            assert not paths[0].exists() and renamed.is_file()
            assert renamed.read_text() == "# Original\n\nText to keep."
            assert (
                evaluate("document.querySelector('.source-editor:not([hidden])').value") == edited
            )
            assert window.bridge.library.get(str(renamed))["annotations"][0]["id"] == note
            assert window.bridge.library.get(str(renamed))["categoryId"] == a
            paths[0] = renamed
            menu(row(str(renamed), True))
            action("save")
            native_wait(lambda: renamed.read_text() == edited)
            print(
                "PASS: rename collision protection; actual rename retains source edits, notes and category",
                flush=True,
            )

            for mode in ("columns", "rows", "grid", "single"):
                menu(row(str(renamed), True))
                action("layout-" + mode)
                assert (
                    evaluate("document.getElementById('document-workspace').dataset.layout") == mode
                )
                assert evaluate("document.getElementById('reading-layout').value") == mode
            mouse(row(str(renamed), True))
            mouse(row(second, True), control=True)
            menu(row(second, True))
            action("layout-columns")
            assert evaluate("readerApp.activeId") in {first, second}
            assert evaluate("document.querySelector('.pane-heading select').value") in {
                first,
                second,
            }
            assert evaluate("document.querySelector('.pane-heading select').value") != evaluate(
                "readerApp.activeId"
            )
            menu(row(second, True))
            action("layout-grid")
            mouse(row(second, True))
            mouse(row(third, True), control=True)
            menu(row(third, True))
            action("layout-grid")
            shown = json.loads(
                evaluate(
                    "JSON.stringify([readerApp.activeId,...document.querySelectorAll('.pane-heading select')].map(v=>typeof v==='string'?v:v.value).filter(Boolean))"
                )
            )
            assert len(shown) == len(set(shown)) == 3, shown
            print(
                "PASS: context-menu layouts match the header and retain document state", flush=True
            )

            # Closing a multi-selection must honor cancellation before removing any tab.
            mouse(row(str(renamed), True))
            mouse(row(second, True), control=True)
            click("edit-mode")
            evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])');e.value+=' edit';e.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )
            menu(row(str(renamed), True))
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                action("close")
            assert len(window.bridge.sessions) == 3
            menu(row(str(renamed), True))
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Discard
            ):
                action("close")
            native_wait(lambda: len(window.bridge.sessions) == 1)
            print("PASS: multi-file close respects unsaved-change cancellation", flush=True)

            saved_categories = window.bridge.library.categories()
            saved_entries = [(e["path"], e["categoryId"]) for e in window.bridge.library.entries()]
            close()
            launch()
            assert window.bridge.library.categories() == saved_categories
            assert [
                (e["path"], e["categoryId"]) for e in window.bridge.library.entries()
            ] == saved_entries
            section("files", True)
            section("library", True)
            section("outline", False)
            QTest.qWait(150)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "categories-light.png"))
            click("theme-button")
            wait(
                "document.body.dataset.theme==='dark' && "
                "[...document.querySelectorAll('.category-toggle,.library-open')].every("
                "node=>getComputedStyle(node).color===getComputedStyle(document.body).color)"
            )
            QTest.qWait(600)  # Let the offscreen compositor present the finished color transitions.
            window.grab().save(str(ROOT / "artifacts" / "categories-dark.png"))
            menu(f'#library-list [data-category-id="{a}"] .category-toggle')
            action("category-delete")
            native_wait(lambda: window.bridge.library.get(str(renamed))["categoryId"] == "")
            assert renamed.read_text() == edited
            assert window.bridge.library.get(str(renamed))["annotations"][0]["id"] == note
            assert not errors, errors
            print(
                "PASS: category order/membership survive restart; deleting a category preserves files and notes",
                flush=True,
            )
            print("Categories smoke test passed.", flush=True)
        finally:
            app.clipboard().clear()
            if window is not None:
                close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
