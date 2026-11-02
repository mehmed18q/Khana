"""Exercise table/flowchart builders and offline SVG rendering in real Qt."""

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
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    console_errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            console_errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-builders-") as folder:
        base = Path(folder)
        window = ReaderWindow(settings_path=base / "settings.ini")
        window.showFullScreen()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda value: values.append(value))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, f"JavaScript timeout: {script[:120]}"
            return values[0]

        def wait_for(script, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(70)
            raise AssertionError(
                f"{label}; console: {console_errors}; diagrams: "
                + str(evaluate("document.querySelector('.diagram-message')?.textContent"))
            )

        def click(name):
            evaluate(f"document.getElementById('{name}').click()")

        def tool(name):
            evaluate(f"document.querySelector('[data-format={name}]').click()")

        def edit(source):
            evaluate(
                "(() => { const e = document.querySelector('.source-editor:not([hidden])'); e.value = "
                + json.dumps(source)
                + "; e.focus(); e.setSelectionRange(e.value.length,e.value.length); e.dispatchEvent(new Event('input',{bubbles:true})); })()"
            )

        def source():
            return evaluate("document.querySelector('.source-editor:not([hidden])').value")

        def set_value(selector, value, event="input"):
            evaluate(
                "(() => { const e=document.querySelector("
                + json.dumps(selector)
                + "); e.value="
                + json.dumps(value)
                + "; e.dispatchEvent(new Event("
                + json.dumps(event)
                + ",{bubbles:true})); })()"
            )

        def key(keycode, modifiers=Qt.KeyboardModifier.ControlModifier):
            QTest.keyClick(window.view.focusProxy() or window.view, keycode, modifiers)
            QTest.qWait(100)

        ready = "document.querySelector('.diagram-frame')?.dataset.status === 'ready'"
        svg = "document.querySelector('.diagram-surface')?.shadowRoot?.querySelector('svg')"
        try:
            wait_for("!!window.readerApp?.activeId", "desktop shell loads")
            click("new-file")
            wait_for("readerApp.activeId.startsWith('untitled:')", "new Markdown draft")
            edit("Keep this text")
            tool("table")
            click("table-cancel")
            QTest.qWait(60)
            assert source() == "Keep this text"
            assert evaluate("document.activeElement.classList.contains('source-editor')")
            tool("table")
            key(Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
            assert not evaluate("document.getElementById('table-dialog').open")
            assert source() == "Keep this text"
            print("PASS: cancel and Escape preserve source and restore focus", flush=True)
            edit("# برنامه کاری\n\n")
            tool("table")
            # A close event from the previous dialog can be delivered after reopening.
            evaluate("document.getElementById('table-dialog').dispatchEvent(new Event('close'))")
            set_value("#table-columns", "2", "change")
            set_value("#table-rows", "2", "change")
            tsv = "مرحله\tComponent\tوضعیت\nشروع\tAPI\tآماده\nبررسی\tReview\tدر انتظار"
            evaluate(
                "(() => {const data=new DataTransfer();data.setData('text/plain',"
                + json.dumps(tsv)
                + ");document.querySelector('#table-grid input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));})()"
            )
            assert evaluate("document.querySelector('#table-columns').value==='3'")
            assert evaluate(
                "document.querySelector('#table-grid input[data-row=\"2\"][data-col=\"2\"]').value==='در انتظار'"
            )
            set_value("#table-columns", "1", "change")
            set_value("#table-columns", "3", "change")
            assert evaluate(
                "document.querySelector('#table-grid input[data-row=\"2\"][data-col=\"2\"]').value==='در انتظار'"
            )
            evaluate(
                "(() => {const data=new DataTransfer();data.setData('text/plain',Array(13).fill('x').join('\t'));document.querySelector('#table-grid input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));})()"
            )
            assert evaluate("!document.getElementById('table-error').hidden")
            click("table-insert")
            wait_for(
                "document.querySelectorAll('#document tbody tr').length === 2",
                "spreadsheet paste expands the table and preserves mixed text",
            )
            assert evaluate("document.querySelector('#document th').dir==='rtl'")
            table_source = source()
            key(Qt.Key.Key_Z)
            assert source() == "# برنامه کاری\n\n", repr(source())
            key(
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            assert source() == table_source
            print("PASS: table insertion is one undo/redo operation", flush=True)

            tool("flowchart")
            click("flow-add-node")
            set_value(".flow-node:last-child input", "Temporary")
            click("flow-add-edge")
            evaluate("document.querySelector('.flow-node:last-child .builder-remove').click()")
            assert evaluate(
                "document.querySelectorAll('.flow-node').length===3 && document.querySelectorAll('.flow-edge').length===2"
            )
            set_value(".flow-node:nth-child(1) input", "شروع Start")
            set_value(".flow-node:nth-child(2) input", "کالا موجود است؟")
            set_value(".flow-node:nth-child(2) select", "decision", "change")
            set_value(".flow-node:nth-child(3) input", "پایان End")
            set_value(".flow-edge:nth-child(2) input", "بله Yes")
            click("flow-add-edge")
            set_value(".flow-edge:last-child select:nth-of-type(1)", "N2", "change")
            set_value(".flow-edge:last-child select:nth-of-type(2)", "N1", "change")
            set_value(".flow-edge:last-child input", "خیر No")
            set_value("#flow-title", "گردش کار — Workflow")
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            window.grab().save(str(artifacts / "flowchart-builder.png"))
            click("flow-insert")
            wait_for(ready, "flowchart with Persian labels, a decision and a cycle renders offline")
            assert evaluate(svg + ".querySelectorAll('.node').length===3")
            assert evaluate(svg + ".textContent.includes('کالا')")
            assert evaluate(
                "(() => {const t="
                + svg
                + ".querySelector('[id^=flowchart-N2-] text');return t.getStartPositionOfChar(0).x > t.getStartPositionOfChar(t.getNumberOfChars()-1).x;})()"
            ), "Persian words must read right to left as one label"
            assert evaluate(svg + ".getBoundingClientRect().width > 100")
            assert evaluate(
                "document.querySelector('.diagram-caption').textContent==='گردش کار — Workflow'"
            )
            (artifacts / "flowchart-rendered.svg").write_text(evaluate(svg + ".outerHTML"))
            flow_source = source()
            key(Qt.Key.Key_Z)
            assert source() == table_source
            key(
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            assert source() == flow_source
            wait_for(ready, "flowchart undo/redo restores its preview")
            evaluate("document.querySelector('.diagram-actions [aria-label=\"Zoom in\"]').click()")
            assert evaluate(
                "document.querySelector('.diagram-actions button:nth-child(2)').textContent.includes('%')"
            )
            evaluate("document.querySelector('.diagram-actions button:nth-child(2)').click()")
            # Verify the native clipboard request without depending on compositor
            # focus: unfocused Wayland test windows cannot own the clipboard.
            with patch("reader.ui.bridge.QApplication.clipboard") as clipboard:
                evaluate("document.querySelector('.diagram-actions button:last-child').click()")
                QTest.qWait(80)
                assert "flowchart TD" in clipboard.return_value.setText.call_args.args[0]
            click("read-mode")
            evaluate("document.querySelector('.diagram-frame').scrollIntoView({block:'center'})")
            QTest.qWait(150)
            window.grab().save(str(artifacts / "flowchart-light.png"))
            click("theme-button")
            wait_for(
                "document.querySelector('.diagram-frame').dataset.theme==='dark' && " + ready,
                "theme change redraws the graph",
            )
            window.grab().save(str(artifacts / "flowchart-dark.png"))
            click("theme-button")
            click("edit-mode")
            md_path = base / "workflow.md"
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(md_path), "Markdown (*.md)"),
            ):
                click("save-button")
                wait_for(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "save table and flowchart",
                )
            assert md_path.read_text() == flow_source
            evaluate("readerApp.command('close')")
            QTest.qWait(100)
            window.bridge.load_paths([md_path])
            wait_for(ready, "saved Markdown reopens as a rendered diagram")

            click("edit-mode")
            edit(
                "```mermaid\nflowchart TD\nA[broken\n```\n\n# Still readable\n\n```mermaid\nflowchart LR\nA --> B\n```"
            )
            wait_for(
                "document.querySelectorAll('.diagram-frame[data-status=error]').length===1 && document.querySelectorAll('.diagram-frame[data-status=ready]').length===1",
                "malformed diagram is isolated; later diagrams still render",
            )
            assert evaluate(
                "document.querySelector('#document h1').textContent.includes('Still readable')"
            )
            assert evaluate(
                "document.querySelector('.diagram-frame[data-status=error] details').open"
            )
            edit(
                '```mermaid\n%%{init: {"securityLevel":"loose","htmlLabels":true,"themeCSS":"body{display:none}"}}%%\nflowchart LR\nA["Safe label"] --> B["End"]\nclick A "javascript:alert(1)"\n```'
            )
            wait_for(ready, "diagram directives cannot enable HTML or script links")
            assert evaluate(
                svg + ".querySelectorAll('foreignObject,script,a[href],image').length===0"
            )
            assert evaluate("getComputedStyle(document.body).display!=='none'")

            set_value("#new-format", "HTML", "change")
            click("new-file")
            wait_for(
                "document.getElementById('editor-name').textContent==='HTML source'",
                "new HTML draft",
            )
            tool("table")
            set_value("#table-columns", "1", "change")
            set_value("#table-rows", "1", "change")
            set_value('#table-grid input[data-row="0"]', "نام")
            set_value('#table-grid input[data-row="1"]', "<script>literal & safe</script>")
            click("table-insert")
            wait_for(
                "document.querySelector('#document td')?.textContent==='<script>literal & safe</script>'",
                "HTML table escapes cell contents",
            )
            tool("flowchart")
            set_value("#flow-direction", "RL", "change")
            set_value(".flow-node:nth-child(2) input", "پردازش API")
            click("flow-insert")
            wait_for(ready, "HTML Mermaid block renders right-to-left flow")
            assert '<code class="language-mermaid">flowchart RL' in source()
            assert evaluate(
                "(() => {const s="
                + svg
                + ";return s.querySelector('[id^=flowchart-N1-]').getBoundingClientRect().x > s.querySelector('[id^=flowchart-N3-]').getBoundingClientRect().x;})()"
            )
            html_source = source()
            html_path = base / "workflow.html"
            with patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(html_path), "HTML (*.html)"),
            ):
                click("save-button")
                wait_for(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "save HTML graph source",
                )
            assert html_path.read_text() == html_source
            evaluate("readerApp.command('close')")
            QTest.qWait(100)
            window.bridge.load_paths([html_path])
            wait_for(ready, "HTML flowchart survives save and reopen")
            # Switching files while jobs are pending must not insert stale SVG.
            window.bridge.load_paths([ROOT / "examples/tables-and-flowcharts.md"])
            wait_for(
                "document.querySelectorAll('.diagram-frame[data-status=ready]').length===2",
                "sample renders multiple diagrams",
            )
            click("edit-mode")
            window.showNormal()
            window.resize(900, 720)
            QTest.qWait(200)
            tool("flowchart")
            assert evaluate(
                "document.getElementById('flow-dialog').getBoundingClientRect().width<=innerWidth"
            )
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            click("flow-cancel")
            assert not console_errors, console_errors
            print("Builder smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(100)
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
