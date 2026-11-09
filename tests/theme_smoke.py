"""Exercise format marks, live system themes, palettes and compact headers in WebEngine."""

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

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow
from reader.word_documents import save_word


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-theme-") as temporary:
        folder = Path(temporary)
        fixtures = {
            "راهنما.md": "# A place to read\n\nمتن فارسی در کنار English.\n\n> Keep your ideas together.\n\n- Read\n- Write\n\n```python\nprint('Hello')\n```\n",
            "Notes.txt": "Plain text",
            "Page.html": "<h1>HTML</h1>",
            "Data.json": '{"hello": "world"}',
            "Config.yaml": "hello: world",
            "Server.log": "INFO Started",
            "Settings.ini": "[reader]\ntheme=auto",
            "Feed.xml": "<root>Text</root>",
        }
        for name, text in fixtures.items():
            (folder / name).write_text(text)
        word = folder / "Report.docx"
        word.write_bytes(save_word("<h1>Report</h1><p>Word document.</p>", ".docx"))
        pdf_path = folder / "Paper.pdf"
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), "PDF document")
            pdf.save(pdf_path)
        paths = [*(folder / name for name in fixtures), word, pdf_path]
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
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if evaluate(script):
                    return
                QTest.qWait(40)
            raise AssertionError(f"{script}: {errors}")

        def click(selector):
            evaluate(f"document.querySelector({json.dumps(selector)}).click()")

        def launch():
            nonlocal window
            window = ReaderWindow(paths, settings_path=settings)
            window.resize(1320, 1000)
            window.show()
            wait("!!window.readerApp && document.querySelectorAll('.file-item').length===10")

        def close():
            nonlocal window
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
            window = None

        def system(mode):
            scheme = Qt.ColorScheme.Dark if mode == "dark" else Qt.ColorScheme.Light
            hints = app.styleHints()
            with patch.object(type(hints), "colorScheme", return_value=scheme):
                hints.colorSchemeChanged.emit(scheme)
            wait(
                f"document.getElementById('theme-system-status').textContent==='System appearance: {mode.title()}'"
            )

        def screenshot(name):
            QTest.qWait(600)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / name))

        try:
            launch()
            kinds = {
                "markdown",
                "text",
                "html",
                "json",
                "yaml",
                "log",
                "conf",
                "xml",
                "word",
                "pdf",
            }
            for scope in ("file-list", "library-list"):
                found = json.loads(
                    evaluate(
                        f"JSON.stringify([...document.querySelectorAll('#{scope} .file-type-icon')].map(n=>n.dataset.fileType))"
                    )
                )
                assert set(found) == kinds and len(found) == 10, found
            evaluate("readerApp.showDocument(" + json.dumps(str(paths[0])) + ")")
            wait("document.querySelector('#current-file-icon svg')?.dataset.fileType==='markdown'")
            print("PASS: ten distinct file format marks in both lists and the header", flush=True)

            click("#theme-settings-button")
            wait("!document.getElementById('theme-panel').hidden")
            colors = set()
            for palette in ("forest", "ocean", "violet", "rose", "amber", "slate"):
                click(f'[data-palette-choice="{palette}"]')
                wait(f"document.body.dataset.palette==='{palette}'")
                colors.add(evaluate("getComputedStyle(document.body).getPropertyValue('--accent')"))
            assert len(colors) == 6
            click('[data-palette-choice="ocean"]')
            screenshot("theme-ocean-light.png")
            click('[data-theme-choice="auto"]')
            system("dark")
            wait("document.body.dataset.theme==='dark' && readerApp.settings.theme==='auto'")
            system("light")
            wait("document.body.dataset.theme==='light' && readerApp.settings.theme==='auto'")
            click('[data-theme-choice="dark"]')
            system("light")
            assert evaluate("document.body.dataset.theme==='dark'")
            click('[data-palette-choice="violet"]')
            screenshot("theme-violet-dark.png")
            click("#theme-close")
            wait("document.getElementById('theme-panel').hidden")
            print(
                "PASS: six palettes, automatic live system changes and manual override", flush=True
            )

            # A rename within the Markdown format updates the extension-specific text mark.
            old = paths[1]
            assert window.bridge.renameFile(str(old), "Notes.md") == ""
            paths[1] = old.with_name("Notes.md")
            wait(
                "document.querySelector('#file-list .file-item[data-id="
                + json.dumps(str(old))
                + "] svg').dataset.fileType==='markdown'"
            )
            click("#edit-mode")
            field = "document.querySelector('.source-editor:not([hidden])')"
            evaluate(
                field
                + ".value+='\\nUnsaved text';"
                + field
                + ".dispatchEvent(new Event('input',{bubbles:true}));"
                + field
                + ".setSelectionRange(3,8)"
            )
            before = evaluate(field + ".value")
            state = window.windowState()
            sidebar_width = evaluate(
                "document.getElementById('sidebar-panel').getBoundingClientRect().width"
            )
            height = evaluate(
                "document.getElementById('document-workspace').getBoundingClientRect().height"
            )
            click("#header-collapse")
            wait(
                "document.body.classList.contains('header-collapsed') && document.querySelector('.compact-header').getClientRects().length>0"
            )
            assert window.windowState() == state and not window.focus_mode
            assert (
                evaluate("document.getElementById('sidebar-panel').getBoundingClientRect().width")
                == sidebar_width
            )
            assert (
                evaluate(
                    "document.getElementById('document-workspace').getBoundingClientRect().height"
                )
                > height + 100
            )
            assert evaluate(field + ".value") == before
            assert evaluate(field + ".selectionStart===3 && " + field + ".selectionEnd===8")
            assert evaluate("document.getElementById('compact-filename').textContent.endsWith('•')")
            screenshot("header-compact-dark.png")
            window.set_focus_mode(True)
            wait("document.body.classList.contains('focus-mode')")
            assert evaluate("!document.querySelector('.compact-header').getClientRects().length")
            window.set_focus_mode(False)
            wait("!document.body.classList.contains('focus-mode')")
            assert evaluate("document.querySelector('.compact-header').getClientRects().length>0")
            click("#header-expand")
            wait("!document.body.classList.contains('header-collapsed')")
            assert evaluate(field + ".value") == before
            print(
                "PASS: compact header preserves editing, selection, sidebar and window state",
                flush=True,
            )

            # Save, retain a split layout while folding the header, then restore preferences.
            click("#save-button")
            wait("document.getElementById('save-status').textContent==='Saved'")
            evaluate(
                "document.getElementById('reading-layout').value='columns';document.getElementById('reading-layout').dispatchEvent(new Event('change'))"
            )
            assert evaluate("document.querySelector('.pane-heading .file-type-icon')!==null")
            click("#header-collapse")
            assert evaluate(
                "document.getElementById('document-workspace').dataset.layout==='columns'"
            )
            close()
            launch()
            wait(
                "document.body.dataset.theme==='dark' && document.body.dataset.palette==='violet' && document.body.classList.contains('header-collapsed')"
            )
            click("#header-expand")
            window.resize(860, 600)
            click("#theme-settings-button")
            wait("!document.getElementById('theme-panel').hidden")
            assert evaluate(
                "(()=>{const r=document.getElementById('theme-panel').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})()"
            )
            assert not errors, errors
            print(
                "PASS: palette/header persistence, split panes and narrow-window controls",
                flush=True,
            )
            print("Theme smoke test passed.", flush=True)
        finally:
            if window is not None:
                close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
