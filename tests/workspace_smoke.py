"""Real WebEngine checks for panes, retained Swagger state, IPC and tab movement."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api_fixture import api_server, api_spec
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.instance import SingleInstance
from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with (
        tempfile.TemporaryDirectory(prefix="khana-workspace-") as tmp,
        api_server() as (url, requests),
    ):
        folder = Path(tmp)
        api_file = folder / "api.json"
        api_file.write_text(json.dumps(api_spec(url)))
        paths = [folder / name for name in ["one.md", "دو با فاصله.md", "three.md"]]
        for path in paths:
            path.write_text("# " + path.name + "\n\n" + ("Paragraph for scrolling.\n\n" * 150))
        window = ReaderWindow([*paths, api_file], settings_path=folder / "settings.ini")
        window.show()
        manager = window.manager
        windows = [window]

        def evaluate(script, target=None):
            values = []
            (target or window).page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(script, label, target=None):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if evaluate("!!window.readerApp && (" + script + ")", target):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(40)
            details = evaluate(
                "JSON.stringify({active:window.readerApp?.activeId,body:document.querySelector('#document')?.innerText.slice(0,1000),toast:document.getElementById('toast')?.textContent,api:document.querySelector('.swagger-host')?.shadowRoot?.querySelector('[data-api-operation=\"GET /public\"]')?.innerText.slice(-1000)})",
                target,
            )
            raise AssertionError(
                f"{label}: {errors}; transfers: {[(t[1], v.prepared, v.delivered) for t, v in manager.transfers.items()]}; {details}"
            )

        def native_wait(condition):
            deadline = time.monotonic() + 15
            while not condition() and time.monotonic() < deadline:
                QTest.qWait(30)
            assert condition()

        def activate(path, target=None):
            evaluate("readerApp.showDocument(" + json.dumps(str(path)) + ")", target)

        def layout(value):
            evaluate(
                "(()=>{const s=document.getElementById('reading-layout');s.value="
                + json.dumps(value)
                + ";s.dispatchEvent(new Event('change'));})()"
            )

        shadow = "document.querySelector('#document .swagger-host')?.shadowRoot"

        def operation(path):
            return (
                shadow + "?.querySelector(" + json.dumps(f'[data-api-operation="GET {path}"]') + ")"
            )

        try:
            wait(shadow + "?.querySelectorAll('[data-api-operation]').length===10", "API loads")
            public = operation("/public")
            evaluate(public + ".querySelector('.opblock-summary-control').click()")
            wait(public + ".querySelector('.try-out__btn')!==null", "public operation expanded")
            evaluate(public + ".querySelector('.try-out__btn').click()")
            wait(public + ".querySelector('.execute')!==null", "public operation ready")
            evaluate(public + ".querySelector('.execute').click()")
            wait(
                public + ".querySelector('.live-responses-table')!==null", "HTTP response rendered"
            )
            evaluate('window.retainedHost=document.querySelector("#document .swagger-host")')
            activate(paths[0])
            activate(api_file)
            wait(
                public + ".querySelector('.live-responses-table')!==null",
                "HTTP response survives tab switching",
            )
            assert evaluate(
                'window.retainedHost===document.querySelector("#document .swagger-host")'
            )
            assert len(requests) == 1, "Returning to a tab must not reissue requests"
            slow = operation("/slow")
            evaluate(slow + ".querySelector('.opblock-summary-control').click()")
            wait(slow + ".querySelector('.try-out__btn')!==null", "slow operation expanded")
            evaluate(slow + ".querySelector('.try-out__btn').click()")
            wait(slow + ".querySelector('.execute')!==null", "slow operation ready")
            evaluate(slow + ".querySelector('.execute').click()")
            native_wait(lambda: bool(window.bridge.api_requests.pending))
            activate(paths[0])
            QTest.qWait(2300)
            activate(api_file)
            wait(
                slow + ".querySelector('.live-responses-table')!==null",
                "background request completes while another tab is open",
            )

            layout("columns")
            assert evaluate("document.querySelectorAll('.extra-pane').length===1")
            assert evaluate(
                "getComputedStyle(document.getElementById('document-workspace')).gridTemplateColumns.split(' ').length===2"
            )
            layout("rows")
            assert evaluate(
                "getComputedStyle(document.getElementById('document-workspace')).gridTemplateRows.split(' ').length===2"
            )
            layout("grid")
            wait(
                "document.querySelectorAll('.extra-pane .document h1').length===3",
                "four distinct files visible",
            )
            evaluate("document.querySelector('.extra-pane .reading-scroll').scrollTop=400")
            QTest.qWait(100)
            assert evaluate("document.querySelector('.extra-pane .reading-scroll').scrollTop>350")
            assert evaluate("document.getElementById('reading-scroll').scrollTop<100")
            evaluate("document.querySelector('.extra-pane .pane-heading button').click()")
            wait(
                "!!document.querySelector('.extra-pane .swagger-host')",
                "focus swaps files without losing the other panes",
            )
            assert evaluate(
                "document.querySelector('.extra-pane .swagger-host')===window.retainedHost"
            )
            extra_shadow = "document.querySelector('.extra-pane .swagger-host').shadowRoot"
            evaluate(
                extra_shadow
                + ".querySelector('[data-api-operation=\"GET /public\"] .execute').click()"
            )
            native_wait(lambda: len(requests) == 3)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "workspace-grid.png"))
            print("PASS: independent scrolling and Swagger requests in secondary panes", flush=True)

            activate(api_file)
            evaluate(slow + ".querySelector('.execute').click()")
            native_wait(lambda: bool(window.bridge.api_requests.pending))
            evaluate("readerApp.detachDocument(readerApp.activeId)")
            native_wait(lambda: len(manager.windows) == 2)
            detached = manager.windows[-1]
            windows.append(detached)
            wait(
                "!!(" + public + "?.querySelector('.live-responses-table'))",
                "detached API retains completed response",
                detached,
            )
            native_wait(lambda: str(api_file) not in window.bridge.sessions)
            assert not window.bridge.api_requests.pending
            assert evaluate("!!(" + slow + "?.querySelector('.live-responses-table'))", detached)
            assert str(api_file) in detached.bridge.sessions
            window.bridge.starDocument(str(api_file), True)
            wait(
                "document.getElementById('star-document').getAttribute('aria-pressed')==='true'",
                "library updates reach another window",
                detached,
            )
            before = len(requests)
            QTest.qWait(300)
            assert len(requests) == before, "Moving must not replay network requests"
            manager.open_paths([str(api_file)])
            assert len(manager.windows) == 2 and manager.recent is detached
            print("PASS: opening an existing file focuses its detached window", flush=True)

            # Native IPC runs in another process, with Unicode/space paths and an acknowledgement.
            instance = SingleInstance(directory=folder, name="instance")
            assert instance.start_or_forward([])
            instance.openRequested.connect(manager.open_paths)
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "from PySide6.QtCore import QCoreApplication; from reader.instance import SingleInstance; import sys; "
                    'app=QCoreApplication([]); i=SingleInstance(directory=sys.argv[1],name="instance"); '
                    "sys.exit(5 if i.start_or_forward(sys.argv[2:]) else 0)",
                    str(folder),
                    str(paths[1]),
                ],
                cwd=ROOT,
            )
            native_wait(lambda: child.poll() is not None)
            assert child.returncode == 0 and len(manager.windows) == 2
            assert manager.recent is window
            instance.close()
            replacement = SingleInstance(directory=folder, name="instance")
            assert replacement.start_or_forward([])
            replacement.close()
            print("PASS: repeated launches forward files and the endpoint can restart", flush=True)
            crashed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from PySide6.QtCore import QCoreApplication; from reader.instance import SingleInstance; import os,sys; "
                    'app=QCoreApplication([]); i=SingleInstance(directory=sys.argv[1],name="crashed"); '
                    "assert i.start_or_forward([]); os._exit(0)",
                    str(folder),
                ],
                cwd=ROOT,
                timeout=10,
            )
            assert crashed.returncode == 0
            recovered = SingleInstance(directory=folder, name="crashed")
            assert recovered.start_or_forward([])
            recovered.close()
            print("PASS: a crashed process does not prevent a fresh launch", flush=True)

            # Move a dirty, never-saved buffer without a save/discard dialog.
            layout("single")
            window.bridge.newDocument("Markdown")
            wait("readerApp.activeId.startsWith('untitled:')", "new draft")
            draft_id = evaluate("readerApp.activeId")
            field = "document.querySelector('.source-editor:not([hidden])')"
            evaluate(
                field
                + ".value='# Unsaved draft\\n\\nسلام';"
                + field
                + ".dispatchEvent(new Event('input',{bubbles:true}))"
            )
            wait(
                "document.querySelector('#document h1')?.textContent==='Unsaved draft'",
                "draft preview",
            )
            evaluate("readerApp.detachDocument(readerApp.activeId)")
            native_wait(lambda: len(manager.windows) == 3)
            draft_window = manager.windows[-1]
            windows.append(draft_window)
            wait(
                field + "?.value.includes('سلام')",
                "draft text moves to another window",
                draft_window,
            )
            native_wait(lambda: draft_id not in window.bridge.sessions)
            assert draft_window.bridge.sessions[draft_id].dirty
            assert draft_window.bridge.sessions[draft_id].saved_source == ""
            assert evaluate(
                "document.querySelector('#document h1')?.textContent==='Unsaved draft'",
                draft_window,
            )

            # Real pointer events must reach the native drag bridge from the tab.
            point = json.loads(
                evaluate(
                    "JSON.stringify((()=>{const r=document.querySelector('.file-item.active .file-select').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())",
                    draft_window,
                )
            )
            start = draft_window.view.mapTo(draft_window, QPoint(round(point[0]), round(point[1])))
            with (
                patch(
                    "reader.ui.bridge.QDrag.exec", return_value=Qt.DropAction.IgnoreAction
                ) as native_drag,
                patch(
                    "reader.ui.bridge.QCursor.pos",
                    return_value=draft_window.frameGeometry().center(),
                ),
            ):
                QTest.mousePress(draft_window.windowHandle(), Qt.MouseButton.LeftButton, pos=start)
                QTest.mouseMove(draft_window.windowHandle(), start + QPoint(35, 12))
                native_wait(lambda: native_drag.called)
                QTest.mouseRelease(
                    draft_window.windowHandle(),
                    Qt.MouseButton.LeftButton,
                    pos=start + QPoint(35, 12),
                )
            print("PASS: dragging a tab invokes the native desktop drag", flush=True)

            # Exercise native drag completion: outside release detaches; Escape and inside release do not.
            def drag(target, cancelled=False, outside=True):
                identifier = evaluate("readerApp.activeId", target)

                def execute(_actions):
                    if cancelled:
                        manager.drag_cancelled = True
                    return Qt.DropAction.IgnoreAction

                point = QPoint(-10000, -10000) if outside else target.frameGeometry().center()
                with (
                    patch(
                        "reader.ui.bridge.QApplication.mouseButtons",
                        return_value=Qt.MouseButton.LeftButton,
                    ),
                    patch("reader.ui.bridge.QDrag.exec", side_effect=execute),
                    patch("reader.ui.bridge.QCursor.pos", return_value=point),
                ):
                    target.bridge.startTabDrag(
                        identifier, target.bridge.sessions[identifier].document.source, "{}"
                    )

            count = len(manager.windows)
            drag(draft_window, cancelled=True)
            drag(draft_window, outside=False)
            assert len(manager.windows) == count
            drag(draft_window)
            native_wait(lambda: manager.windows[-1] is not draft_window)
            moved = manager.windows[-1]
            windows.append(moved)
            wait(
                "readerApp.activeId===" + json.dumps(draft_id),
                "release outside creates a window",
                moved,
            )
            native_wait(lambda: draft_window not in manager.windows)
            assert len(manager.windows) == count
            print(
                "PASS: Escape cancels drag; last-tab transfer closes the empty source window",
                flush=True,
            )
            manager.dragging = (
                moved,
                draft_id,
                moved.bridge.sessions[draft_id].document.source,
                "{}",
            )
            mime = QMimeData()
            mime.setData("application/x-khana-tab", draft_id.encode())
            drop = QDropEvent(
                QPointF(window.view.rect().center()),
                Qt.DropAction.MoveAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            window.view.dropEvent(drop)
            manager.dragging = None
            assert drop.isAccepted()
            native_wait(lambda: draft_id in window.bridge.sessions and moved not in manager.windows)
            wait(
                field + "?.value.includes('سلام')",
                "dropping a tab into an existing window preserves the draft",
            )
            manager.transfer(
                window,
                draft_id,
                window.bridge.sessions[draft_id].document.source,
                "{}",
                target=detached,
            )
            manager.abort_transfer(detached, draft_id)
            QTest.qWait(200)
            assert draft_id in window.bridge.sessions and draft_id not in detached.bridge.sessions
            assert evaluate(field + ".readOnly===false")
            print("PASS: a failed transfer leaves the original draft editable", flush=True)
            # Hold a transfer while exercising shortcuts and a rejected window close.
            with (
                patch.object(manager, "prepare_transfer"),
                patch.object(window.bridge, "_save_session") as save,
                patch("reader.ui.bridge.load_document") as reload,
            ):
                manager.transfer(
                    window,
                    draft_id,
                    window.bridge.sessions[draft_id].document.source,
                    "{}",
                    target=detached,
                )
                wait(field + ".readOnly===true", "moving draft is locked")
                evaluate(
                    "readerApp.command('save-as'); readerApp.command('reload'); readerApp.command('quit-request')"
                )
                wait(
                    "document.getElementById('toast').textContent.includes('finish moving')",
                    "closing waits for tab transfer",
                )
                QTest.qWait(100)
                assert evaluate(field + ".readOnly===true"), (
                    "Rejected quit must not unlock a moving draft"
                )
                save.assert_not_called()
                reload.assert_not_called()
                manager.abort_transfer(detached, draft_id)
                wait(field + ".readOnly===false", "aborting transfer restores editing")
            if errors:
                print("CONSOLE ERRORS:", errors, flush=True)
            assert not errors, errors
            print("Workspace smoke test passed.", flush=True)
        finally:
            for target in windows:
                target.allow_close = True
                target.close()
                target.page.deleteLater()
                QTest.qWait(100)
            QTest.qWait(150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
