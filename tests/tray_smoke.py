"""Exercise close choices and unsaved buffers with an emulated system tray."""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication, QMessageBox

from reader.ui.window import ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="khana-tray-") as temporary:
        folder = Path(temporary)
        path = folder / "document.md"
        path.write_text("# Saved\n")
        window = ReaderWindow([path], settings_path=folder / "settings.ini")
        window.show()
        manager = window.manager
        tray = manager.tray

        def js(script, target=window):
            values = []
            target.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 15
            while not values and time.monotonic() < deadline:
                QTest.qWait(15)
            assert values, script
            return values[0]

        def wait(condition):
            deadline = time.monotonic() + 20
            while not condition():
                assert time.monotonic() < deadline
                QTest.qWait(30)

        def ask():
            """Close the window and wait for the page's close prompt."""
            window.close()
            wait(lambda: js("document.getElementById('close-dialog').open"))

        def answer(value, remember=False):
            js(
                "document.getElementById('close-remember').checked="
                + ("true" if remember else "false")
                + ";document.querySelector('#close-dialog [value=\""
                + value
                + "\"]').click()"
            )
            wait(lambda: not js("document.getElementById('close-dialog').open"))
            QTest.qWait(50)

        try:
            wait(lambda: js("!!window.readerApp?.activeId"))
            assert tray.icon is None or tray.icon.isVisible()
            assert not app.quitOnLastWindowClosed()

            # The page asks, as Bandar does; Cancel keeps everything as it was.
            with patch.object(tray, "available", return_value=False):
                ask()
            assert "applications menu" in js("document.getElementById('close-hint').textContent")
            answer("cancel")
            assert window.isVisible() and window in manager.windows
            js("readerApp.setEditMode(true)")
            js(
                "window.field=document.querySelector('.source-editor');field.focus();field.setSelectionRange(field.value.length,field.value.length);document.execCommand('insertText',false,'Unsaved متن')"
            )
            source = js("field.value")
            ask()
            assert "1" in js("document.getElementById('close-message').textContent")
            assert js("document.activeElement.id") == "close-background"
            answer("background")
            wait(lambda: not window.isVisible())
            assert window in manager.windows and path.read_text() == "# Saved\n"
            tray.restore()
            assert window.isVisible()
            assert js("field.value") == source
            js("field.focus();document.execCommand('undo')")
            assert js("field.value") == "# Saved\n"
            js("document.execCommand('redo')")
            assert js("field.value") == source

            # A remembered choice is saved and applies without asking again.
            ask()
            answer("background", remember=True)
            wait(lambda: not window.isVisible())
            assert window.bridge.preferences()["closeAction"] == "background"
            tray.restore()
            window.close()
            wait(lambda: not window.isVisible())
            assert not js("document.getElementById('close-dialog').open")
            tray.restore()
            js("readerApp.preferences()")  # the page saves its own copy of the setting
            assert window.bridge.preferences()["closeAction"] == "background"
            js(
                "document.getElementById('settings-button').click();"
                'document.querySelector(\'#settings-dialog [data-setting="closeAction"][data-value="ask"]\').click();'
                "document.getElementById('settings-dialog').close()"
            )
            wait(lambda: window.bridge.preferences()["closeAction"] == "ask")
            print(
                "PASS: close prompt, background, remembered choice, tray restore, buffer and undo",
                flush=True,
            )

            # One menu exits every window, stopping safely on a canceled save.
            other = ReaderWindow(
                settings_path=manager.settings_path, manager=manager, restore_session=False
            )
            other.show()
            wait(lambda: other.bridge.initialized)
            other.bridge.newDocument("Markdown")
            wait(lambda: js("!!readerApp.activeId", other))
            js(
                "document.querySelector('.source-editor').focus();document.execCommand('insertText',false,'Second draft')",
                other,
            )
            with patch.object(
                window.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel
            ):
                tray.quit_all()
                wait(lambda: not window.close_pending and not tray.exiting)
            assert len(manager.windows) == 2 and window.isVisible()
            assert js("field.value") == source
            with patch.object(other.bridge, "_ask", return_value=QMessageBox.StandardButton.Cancel):
                other.request_exit()
                wait(lambda: not other.close_pending)
            assert other.isVisible()

            # Browser errors, slow tasks and renderer exits reach persistent logs.
            js(
                "console.error('diagnostic-smoke');window.dispatchEvent(new ErrorEvent('error',{message:'browser-error-smoke',filename:'smoke.js',lineno:7}));setTimeout(()=>{const start=performance.now();while(performance.now()-start<160){}},0)"
            )
            window.page.renderProcessTerminated.emit(
                QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus, 23
            )
            log = folder / "logs" / "khana.log"
            wait(
                lambda: (
                    "browser-error-smoke" in log.read_text()
                    and "Browser slow-task" in log.read_text()
                )
            )
            assert "diagnostic-smoke" in log.read_text()
            assert "Renderer terminated" in log.read_text()
            with patch("reader.ui.bridge.QDesktopServices.openUrl", return_value=True) as opened:
                window.bridge.openLogs()
                assert opened.call_args.args[0].toLocalFile() == str(folder / "logs")
            print("PASS: browser, renderer and slow-operation logs", flush=True)

            target = folder / "second.md"
            with (
                patch.object(window.bridge, "_ask", return_value=QMessageBox.StandardButton.Save),
                patch.object(other.bridge, "_ask", return_value=QMessageBox.StandardButton.Save),
                patch(
                    "reader.ui.bridge.QFileDialog.getSaveFileName", return_value=(str(target), "")
                ),
                patch.object(app, "quit") as quit_app,
            ):
                tray.quit_all()
                wait(lambda: not manager.windows)
                assert quit_app.called
            assert path.read_text() == source
            assert target.read_text() == "Second draft"
            assert not window.isVisible() and not other.isVisible()
            print("PASS: tray exit saves latest changes in every window", flush=True)
        finally:
            for item in list(manager.windows):
                item.allow_close = True
                item.close()
            window.page.deleteLater()
            if "other" in locals():
                other.page.deleteLater()
            QTest.qWait(150)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
