"""Real desktop verification of formats, images, PDF text, and scroll mapping."""

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow
from reader.word_documents import load_word, save_word


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(message)

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-formats-") as folder:
        root = Path(folder)
        docs = root / "docs"
        docs.mkdir()
        source = "\n\n".join(
            f"## Section {i}\n\nParagraph {i}: Persian فارسی English." for i in range(100)
        )
        md = docs / "long.md"
        md.write_text(source)
        image = QImage(120, 80, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.green)
        photo = root / "عکس sample.png"
        image.save(str(photo))
        window = ReaderWindow([md], settings_path=root / "settings.ini")
        window.showFullScreen()
        pdf_responses = []
        window.bridge.pdfPageReady.connect(lambda raw: pdf_responses.append(json.loads(raw)))

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda value: values.append(value))
            end = time.monotonic() + 10
            while not values and time.monotonic() < end:
                QTest.qWait(20)
            assert values, script[:100]
            return values[0]

        def wait(script, label):
            end = time.monotonic() + 25
            while time.monotonic() < end:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            details = evaluate(
                "JSON.stringify({active:readerApp.activeId,toast:document.getElementById('toast').textContent,pdf:document.querySelector('.pdf-page')?.getBoundingClientRect().toJSON(),scroll:document.getElementById('reading-scroll').scrollTop,image:document.querySelector('.pdf-image')?.outerHTML,loading:document.querySelector('.pdf-loading')?.textContent})"
            )
            raise AssertionError(
                f"{label}: {errors}; {details}; pending PDF tasks: {list(window.bridge.jobs.pdf_pages)}; PDF responses: {pdf_responses}"
            )

        def click(name):
            evaluate(f"document.getElementById('{name}').click()")

        def open_file(path):
            window.bridge.load_paths([path])
            wait(
                'document.getElementById("current-filename").textContent==='
                + json.dumps(path.name),
                "open " + path.suffix,
            )

        def edit(text):
            evaluate(
                "(() => { const e=document.querySelector('.source-editor:not([hidden])'),start=e.selectionStart,top=e.scrollTop; e.value="
                + json.dumps(text)
                + "; e.setSelectionRange(start,start);e.scrollTop=top;e.dispatchEvent(new Event('input',{bubbles:true})); })()"
            )
            wait(
                "document.getElementById('preview-status').textContent==='Live preview'",
                "preview updates",
            )

        def preview_near(line):
            return (
                "(() => {const p=document.querySelector('#document [data-source-line=\""
                + str(line)
                + "\"]');const r=p.getBoundingClientRect(),s=document.getElementById('reading-scroll').getBoundingClientRect();return r.top>=s.top-80&&r.top<s.top+130;})()"
            )

        try:
            wait("document.querySelectorAll('#document h2').length===100", "long Markdown loads")
            click("edit-mode")
            QTest.qWait(250)
            evaluate(
                "(() => {const e=document.querySelector('.source-editor:not([hidden])');e.scrollTop=160*parseFloat(getComputedStyle(e).lineHeight);})()"
            )
            wait(preview_near(160), "editor scroll follows source lines into preview")
            evaluate(
                "document.querySelector('#document [data-source-line=\"240\"]').scrollIntoView({block:'start',behavior:'instant'})"
            )
            wait(
                "(() => {const e=document.querySelector('.source-editor:not([hidden])');return Math.abs(e.scrollTop/parseFloat(getComputedStyle(e).lineHeight)-240)<6;})()",
                "preview scroll follows back into editor",
            )
            a = evaluate("document.querySelector('.source-editor:not([hidden])').scrollTop")
            QTest.qWait(400)
            b = evaluate("document.querySelector('.source-editor:not([hidden])').scrollTop")
            assert abs(a - b) < 2, (a, b)
            click("sync-scroll")
            old = evaluate("document.getElementById('reading-scroll').scrollTop")
            evaluate("document.querySelector('.source-editor:not([hidden])').scrollTop=0")
            QTest.qWait(150)
            assert abs(evaluate("document.getElementById('reading-scroll').scrollTop") - old) < 2
            click("sync-scroll")
            QTest.qWait(150)
            evaluate(
                "(() => {const e=document.querySelector('.source-editor:not([hidden])');const n=e.value.indexOf('Paragraph 60:');e.setSelectionRange(n,n);})()"
            )
            # Live re-render stays near the current editing location.
            edit(source.replace("Paragraph 60:", "Edited paragraph 60:"))
            wait(preview_near(240), "live preview retains the editing location")
            evaluate("readerApp.command('save')")
            QTest.qWait(100)
            with patch(
                "reader.ui.bridge.QFileDialog.getOpenFileName", return_value=(str(photo), "")
            ):
                evaluate("document.querySelector('[data-format=image]').click()")
                wait(
                    "document.querySelector('#document img')?.naturalWidth===120",
                    "Markdown image loads from an absolute path outside the document folder",
                )
            assert "file:///" in evaluate(
                "document.querySelector('.source-editor:not([hidden])').value"
            )
            evaluate("readerApp.command('save')")
            QTest.qWait(100)
            for suffix, content, target in [
                (".html", "\n".join(f"<p>HTML paragraph {i}</p>" for i in range(120)), 60),
                (".json", "[\n" + ",\n".join(f'  {{"row": {i}}}' for i in range(120)) + "\n]", 60),
            ]:
                path = docs / ("sync" + suffix)
                path.write_text(content)
                open_file(path)
                click("edit-mode")
                QTest.qWait(180)
                evaluate(
                    f"(() => {{const e=document.querySelector('.source-editor:not([hidden])');e.scrollTop={target}*parseFloat(getComputedStyle(e).lineHeight);}})()"
                )
                wait(preview_near(target), "editor-to-preview sync " + suffix)
                evaluate(
                    "document.querySelector('#document [data-source-line=\"90\"]').scrollIntoView({block:'start',behavior:'instant'})"
                )
                wait(
                    "(() => {const e=document.querySelector('.source-editor:not([hidden])');return Math.abs(e.scrollTop/parseFloat(getComputedStyle(e).lineHeight)-90)<6;})()",
                    "preview-to-editor sync " + suffix,
                )
            for ext, _fmt, text in [
                ("json", "JSON", '{\n "name": "سلام"\n}'),
                ("yml", "YAML", "name: سلام\nvalue: 2\n"),
                ("log", "LOG", "[INFO] <script>text</script>"),
                ("conf", "CONF", "[app]\nkey=value"),
                ("xml", "XML", "<root><name>سلام</name></root>"),
            ]:
                path = docs / ("sample." + ext)
                path.write_text(text)
                open_file(path)
                click("edit-mode")
                assert evaluate("document.getElementById('format-toolbar').hidden")
                assert evaluate("document.querySelector('#document pre code').textContent") == text
                evaluate("document.querySelector('.source-editor:not([hidden])').focus()")
                QTest.keyClick(
                    window.view.focusProxy() or window.view,
                    Qt.Key.Key_B,
                    Qt.KeyboardModifier.ControlModifier,
                )
                assert (
                    evaluate("document.querySelector('.source-editor:not([hidden])').value") == text
                )
                edit(text + "\n")
                evaluate("readerApp.command('save')")
                QTest.qWait(100)
                assert path.read_text() == text + "\n"
            # Word imports/exports via the actual Writer process, for both formats.
            for suffix in [".docx", ".doc"]:
                path = docs / ("word" + suffix)
                path.write_bytes(
                    save_word(
                        '<!doctype html><meta charset="utf-8"><h1>Word title</h1><p><strong>Bold</strong> سلام</p>',
                        suffix,
                    )
                )
                open_file(path)
                wait(
                    "document.querySelector('#document strong,b')!==null", "Word formatting imports"
                )
                click("edit-mode")
                assert evaluate("!document.getElementById('format-toolbar').hidden")
                edit(
                    '<!doctype html><meta charset="utf-8"><h1>Changed title</h1><p><em>Italic</em> فارسی</p>'
                )
                with patch(
                    "reader.ui.bridge.QFileDialog.getOpenFileName", return_value=(str(photo), "")
                ):
                    evaluate("document.querySelector('[data-format=image]').click()")
                    wait(
                        "document.querySelector('#document img')?.naturalWidth===120",
                        "Word image insertion previews",
                    )
                evaluate("readerApp.command('save')")
                wait(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "Word saves " + suffix,
                )
                reopened = load_word(path.read_bytes(), suffix)
                assert "Changed title" in reopened and "<img" in reopened
            pdf_path = docs / "sample.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((70, 100), "Original PDF text", fontsize=18)
                page.insert_text((70, 200), "Keep this paragraph", fontsize=14)
                pdf.save(pdf_path)
            open_file(pdf_path)
            wait("document.querySelector('.pdf-image')?.naturalWidth>0", "PDF page renders")
            click("edit-mode")
            assert evaluate("document.getElementById('format-toolbar').hidden")
            evaluate("document.querySelector('.pdf-edit').click()")
            wait("document.getElementById('pdf-dialog').open", "PDF text editor opens")
            evaluate("document.getElementById('pdf-text-input').value='Updated PDF text'")
            click("pdf-apply")
            wait(
                "!document.getElementById('pdf-dialog').open && document.querySelector('.pdf-text').textContent==='Updated PDF text'",
                "simple PDF text updates",
            )
            evaluate("readerApp.command('save')")
            wait("document.getElementById('save-status').textContent==='Saved'", "PDF saves")
            with pymupdf.open(pdf_path) as pdf:
                assert (
                    "Updated PDF text" in pdf[0].get_text()
                    and "Keep this paragraph" in pdf[0].get_text()
                )
            state_changes = QSignalSpy(window.windowHandle().windowStateChanged)
            click("minimize-button")
            QTest.qWait(250)
            # Wayland clears the local minimized flag after sending set_minimized.
            assert any(
                state_changes.at(i)[0] == Qt.WindowState.WindowMinimized
                for i in range(state_changes.count())
            )
            window.showFullScreen()
            QTest.qWait(250)
            assert not window.isMinimized()
            print("PASS: minimize and restore preserve the document", flush=True)
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            window.grab().save(str(artifacts / "formats-pdf.png"))
            assert not errors, errors
            window.close()
            QTest.qWait(200)
            assert not window.isVisible()
            print("Formats and scroll synchronization smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(100)
            window.page.deleteLater()
            QTest.qWait(50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
