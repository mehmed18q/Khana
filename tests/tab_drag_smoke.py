"""Exercise Qt's real drag loop, including its internal QObject lifetime.

Use X11/XWayland on Linux: synthetic QTest input has no Wayland pointer serial,
so a Wayland QDrag can be rejected before entering the loop we need to verify.
Only the final screen position is controlled; QDrag.exec is never mocked.
"""

from __future__ import annotations

import faulthandler
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_native_checks():
    from PySide6.QtCore import QPoint, Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from reader.ui.window import ReaderWindow

    faulthandler.enable()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix="khana-native-drag-") as temporary:
        folder = Path(temporary)
        path = folder / "keep.md"
        path.write_text("# Keep this file\n", encoding="utf-8")
        origin = ReaderWindow([path], settings_path=folder / "settings.ini")
        origin.resize(920, 700)
        origin.show()
        manager = origin.manager
        windows = [origin]

        def evaluate(window, script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(condition, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if condition():
                    return
                QTest.qWait(30)
            raise AssertionError(label)

        def drag(window, *, cancel=False, outside=True):
            window.raise_()
            window.activateWindow()
            identifier = evaluate(window, "readerApp.activeId")
            source = window.bridge.sessions[identifier].document.source
            x, y = json.loads(
                evaluate(
                    window,
                    "JSON.stringify((()=>{const r=document.querySelector('.file-item.active .file-select').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())",
                )
            )
            point = window.view.mapTo(window, QPoint(round(x), round(y)))
            reached_loop = []
            timer = QTimer()
            timer.setSingleShot(True)

            def finish():
                reached_loop.append(True)
                assert manager.dragging is not None
                # A second queued browser message must not nest another drag.
                window.bridge.startTabDrag(identifier, source, "{}")
                if cancel:
                    QTest.keyClick(window.windowHandle(), Qt.Key.Key_Escape)
                else:
                    QTest.mouseRelease(window.windowHandle(), Qt.MouseButton.LeftButton, pos=point)

            timer.timeout.connect(finish)
            position = QPoint(-1000, -1000) if outside else window.frameGeometry().center()
            QTest.mousePress(window.windowHandle(), Qt.MouseButton.LeftButton, pos=point)
            timer.start(250)
            try:
                with patch("reader.ui.bridge.QCursor.pos", return_value=position):
                    window.bridge.startTabDrag(identifier, source, "{}")
            finally:
                timer.stop()
                if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                    QTest.mouseRelease(window.windowHandle(), Qt.MouseButton.LeftButton, pos=point)
            assert reached_loop, "The platform rejected the drag before its real event loop ran"
            assert manager.dragging is None
            QTest.qWait(100)

        try:
            wait(lambda: evaluate(origin, "!!window.readerApp?.activeId"), "initial document")
            origin.bridge.newDocument("Markdown")
            wait(
                lambda: evaluate(origin, "readerApp.activeId?.startsWith('untitled:')"),
                "draft opens",
            )
            draft_id = evaluate(origin, "readerApp.activeId")
            source = "# Unsaved drag\n\nمتن ذخیره‌نشده"
            editor = "document.querySelector('.source-editor:not([hidden])')"
            evaluate(
                origin,
                f"{editor}.value={json.dumps(source)};{editor}.dispatchEvent(new Event('input',{{bubbles:true}}))",
            )
            wait(
                lambda: evaluate(
                    origin, "document.querySelector('#document h1')?.textContent==='Unsaved drag'"
                ),
                "draft preview",
            )

            drag(origin, cancel=True)
            assert manager.windows == [origin] and draft_id in origin.bridge.sessions
            assert evaluate(origin, "!document.body.classList.contains('tab-dragging')")
            print(
                "PASS: real Qt drag cancels with Escape without crashing or detaching", flush=True
            )

            drag(origin, outside=False)
            assert manager.windows == [origin] and draft_id in origin.bridge.sessions
            print("PASS: real Qt release inside the source keeps its tabs", flush=True)

            drag(origin)
            wait(lambda: len(manager.windows) == 2, "outside release creates a window")
            moved = manager.windows[-1]
            windows.append(moved)
            wait(lambda: not manager.transfers, "first transfer acknowledged")
            assert str(path) in origin.bridge.sessions and draft_id not in origin.bridge.sessions
            assert moved.bridge.sessions[draft_id].document.source == source
            assert moved.bridge.sessions[draft_id].dirty
            print("PASS: real Qt outside release preserves the unsaved buffer", flush=True)

            drag(moved, cancel=True)
            assert moved in manager.windows and draft_id in moved.bridge.sessions
            drag(moved)
            wait(
                lambda: moved not in manager.windows and not manager.transfers,
                "last tab acknowledged",
            )
            destination = manager.windows[-1]
            windows.append(destination)
            assert len(manager.windows) == 2
            assert destination.bridge.sessions[draft_id].document.source == source
            assert destination.bridge.sessions[draft_id].dirty
            assert evaluate(destination, editor + ".value") == source
            assert not moved.isVisible()
            print(
                "PASS: repeated real drags close an empty source only after acknowledgment",
                flush=True,
            )
        finally:
            for window in set(windows + manager.windows):
                window.allow_close = True
                window.close()
                window.page.deleteLater()
            QTest.qWait(100)
    return 0


def main():
    if "--native-child" in sys.argv:
        return run_native_checks()
    env = dict(os.environ)
    if sys.platform == "linux":
        if not env.get("DISPLAY"):
            raise RuntimeError("The native drag check requires an X11/XWayland DISPLAY.")
        env["QT_QPA_PLATFORM"] = "xcb"
        libraries = ROOT / "build/linux-libs/root/usr/lib/x86_64-linux-gnu"
        if libraries.is_dir():
            env["LD_LIBRARY_PATH"] = str(libraries) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return subprocess.run(
        [sys.executable, __file__, "--native-child"], env=env, timeout=120
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
