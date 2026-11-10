"""Real WebEngine regressions for language, structure editing and scoped spelling."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Synthetic key events cannot acquire Wayland clipboard ownership. Exercise the
# real WebEngine and Qt clipboard using the same offscreen setup as file_menu.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu"
    ).strip()

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-features-") as folder:
        base = Path(folder)
        path = base / "first.md"
        path.write_text(
            "hello helllo سلام سللام\n\n| A | B |\n| :--- | ---: |\n| one | two |\n| three | four |\n"
        )
        second = base / "second.md"
        second.write_text("hello helllo سلام سللام")
        window = ReaderWindow([path], settings_path=base / "settings.ini")
        window.resize(1320, 900)
        window.show()

        def js(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 12
            while not values and time.monotonic() < deadline:
                QTest.qWait(15)
            assert values, script
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if js(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            raise AssertionError(f"{label}: {errors}")

        def click(identifier):
            js(f"document.getElementById({json.dumps(identifier)}).click()")
            QTest.qWait(80)

        def value(selector, value, event="input"):
            js(
                f"(()=>{{const n=document.querySelector({json.dumps(selector)});n.value={json.dumps(value)};n.dispatchEvent(new Event({json.dumps(event)},{{bubbles:true}}))}})()"
            )

        source = "document.querySelector('.source-editor:not([hidden])')"
        count = "CSS.highlights.get('reader-spelling')?.size"

        def spelling_menu(word):
            js(
                """(()=>{const m=document.querySelector('.spelling-text'),r=new Range();const i=m.textContent.indexOf(%s);r.setStart(m.firstChild,i+1);r.setEnd(m.firstChild,i+2);const b=r.getBoundingClientRect();%s.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:b.x+b.width/2,clientY:b.y+b.height/2}));})()"""
                % (json.dumps(word), source)
            )
            wait(
                "!!document.querySelector('#file-context-menu [data-action=ignore-document]')",
                "spelling menu offers both scopes",
            )

        try:
            wait("!!window.readerApp?.activeId", "shell loaded")
            click("ui-language-button")
            assert js("document.querySelectorAll('#ui-language-menu .language-flag').length===2")
            js("document.querySelector('#ui-language-menu [data-value=fa]').click()")
            value("#ui-language", "fa", "change")
            wait(
                "document.documentElement.dir==='rtl' && document.getElementById('save-button').textContent.includes('ذخیره')",
                "Persian labels and RTL",
            )
            assert js(
                "document.querySelector('.sidebar').getBoundingClientRect().left>innerWidth/2"
            )
            assert js("document.getElementById('current-filename').textContent==='first.md'")
            value("#ui-language", "en", "change")
            wait(
                "document.documentElement.dir==='ltr' && document.getElementById('save-button').textContent.includes('Save')",
                "English labels restored",
            )
            assert js("document.querySelector('.sidebar').getBoundingClientRect().left===0")
            click("edit-mode")
            wait(f"{count}>=2", "both dictionaries mark misspellings")
            spelling_menu("helllo")
            wait(
                "!!document.querySelector('[data-action=spelling-suggestion]')",
                "English spelling suggestions",
            )
            js("document.querySelector('[data-action=ignore-document]').click()")
            wait(f"{count}===1", "ignore word for this document")
            click("spellcheck-button")
            assert js(
                "!CSS.highlights.has('reader-spelling') && document.querySelector('.spelling-layer').hidden"
            )
            click("spellcheck-button")
            wait(f"{count}===1", "header switch restores scoped spelling")
            window.bridge.load_paths([second])
            wait(
                "document.getElementById('current-filename').textContent==='second.md'",
                "second document",
            )
            click("edit-mode")
            wait(f"{count}===2", "document ignore does not leak to another file")
            spelling_menu("helllo")
            js("document.querySelector('[data-action=ignore-all]').click()")
            wait(f"{count}===1", "global ignore applies")
            spelling_menu("سللام")
            wait(
                "!!document.querySelector('[data-action=spelling-suggestion]')",
                "Persian suggestions",
            )
            js("document.querySelector('[data-action=spelling-suggestion]').click()")
            wait(f"{count}===0", "suggested correction updates spelling")
            assert "سلام سلام" in js(source + ".value")
            js(source + ".focus();document.execCommand('undo')")
            wait(f"{count}===1", "spelling replacement is undoable")
            window.bridge.load_paths([path])
            wait(
                "document.getElementById('current-filename').textContent==='first.md'",
                "return to table",
            )
            value("#ui-language", "fa", "change")
            QTest.qWait(100)
            js("document.querySelector('.structure-edit').click()")
            wait("document.getElementById('table-dialog').open", "existing table opens for editing")
            assert js(
                "document.querySelector('#table-grid input[data-row=\"1\"][data-col=\"0\"]').value==='one'"
            )
            js(
                'document.querySelector(\'#table-grid input[data-row="1"][data-col="0"]\').focus();document.querySelector(\'#table-grid input[data-row="1"][data-col="0"]\').select()'
            )
            QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_Down)
            assert js("document.activeElement.dataset.row==='2'")
            js(
                'document.querySelector(\'#table-grid input[data-row="2"][data-col="0"]\').focus();document.activeElement.select()'
            )
            QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_Left)
            assert js("document.activeElement.dataset.col==='1'"), js(
                "JSON.stringify({dir:document.documentElement.dir,grid:getComputedStyle(document.getElementById('table-grid')).direction,active:document.activeElement.outerHTML,start:document.activeElement.selectionStart,end:document.activeElement.selectionEnd})"
            )
            QTest.keyClick(window.view.focusProxy(), Qt.Key.Key_Right)
            assert js("document.activeElement.dataset.col==='0'")
            js(
                "(()=>{const data=new DataTransfer();document.querySelector('[data-move-row=\"2\"]').dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:data}));document.querySelector('#table-grid input[data-row=\"1\"]').dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:data}));})()"
            )
            assert js("document.querySelector('#table-grid input[data-row=\"1\"]').value==='three'")
            js("document.querySelector('[data-move-row=\"2\"]').focus()")
            QTest.keyClick(
                window.view.focusProxy(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier
            )
            QTest.qWait(80)
            assert window.bridge.clipboardText() == "one\ttwo\n"
            js("document.querySelector('#table-grid input[data-row=\"1\"]').focus()")
            click("table-copy-row")
            click("table-paste-row")
            assert js("document.getElementById('table-rows').value==='3'")
            click("table-insert")
            wait(
                "document.querySelectorAll('#document tbody tr').length===3",
                "table edits replace the original",
            )
            assert js(source + ".value.includes('| :--- | ---: |')")
            assert js("document.querySelectorAll('#document table').length===1")
            js(source + ".focus();document.execCommand('undo')")
            wait(
                "document.querySelectorAll('#document tbody tr').length===2",
                "table edit is one undo operation",
            )
            js(source + ".setSelectionRange(0,5)")
            js(
                source
                + ".dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:500,clientY:400}))"
            )
            js("document.querySelector('[data-action=cut]').click()")
            assert not js(source + ".value.startsWith('hello')")
            js(source + ".focus();document.execCommand('undo')")
            assert js(source + ".value.startsWith('hello')")
            print("PASS: source context cut and undo", flush=True)
            value("#ui-language", "fa", "change")
            QTest.qWait(150)
            window.grab().save(str(ROOT / "artifacts/features-fa.png"))
            click("ui-language-button")
            window.grab().save(str(ROOT / "artifacts/language-menu.png"))
            js("document.getElementById('ui-language-menu').hidePopover()")
            click("new-format-button")
            window.grab().save(str(ROOT / "artifacts/format-menu.png"))
            js("document.getElementById('new-format-menu').hidePopover()")
            value("#ui-language", "en", "change")
            flow = js(
                "ReaderInsertions.flowchart({nodes:[{id:'N1',shape:'terminal',label:'Start'},{id:'N2',shape:'decision',label:'Continue?'}],edges:[{from:'N1',to:'N2',label:'Yes'}]})"
            )
            value(".source-editor:not([hidden])", flow)
            wait(
                "!!document.querySelector('.diagram-frame[data-status=ready]')",
                "flowchart ready for editing",
            )
            js("document.querySelector('.structure-edit').click()")
            wait(
                "document.getElementById('flow-dialog').open",
                "existing flowchart reopens as steps and edges",
            )
            value(".flow-node input", "شروع")
            click("flow-insert")
            wait(
                "document.querySelector('.diagram-frame[data-status=ready]') && document.querySelector('.diagram-source').textContent.includes('شروع')",
                "flowchart edit replaces original",
            )
            assert js("document.querySelectorAll('.diagram-frame').length===1")
            js(source + ".focus();document.execCommand('undo')")
            assert js(source + ".value") == flow
            value("#new-format", "HTML", "change")
            click("new-file")
            wait(
                "document.getElementById('editor-name').textContent==='HTML source'",
                "HTML editing draft",
            )
            html = '<table class="keep"><thead><tr><th>Title</th><th>Value</th></tr></thead><tbody><tr class="row"><td><strong>Bold</strong></td><td>old</td></tr></tbody></table>'
            value(".source-editor:not([hidden])", html)
            wait("!!document.querySelector('#document strong')", "HTML table loaded")
            js("document.querySelector('.structure-edit').click()")
            value('#table-grid input[data-row="1"][data-col="1"]', "new")
            click("table-insert")
            wait(
                "document.querySelector('#document td:last-child')?.textContent==='new'",
                "HTML cell edit saved",
            )
            assert "<strong>Bold</strong>" in js(source + ".value")
            assert 'class="keep"' in js(source + ".value")
            assert 'class="row"' in js(source + ".value")
            print("PASS: HTML cell edits preserve existing markup and attributes", flush=True)
            assert not errors, errors
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0 if app else 1


if __name__ == "__main__":
    raise SystemExit(main())
