"""Exercise find/replace against real source editors, rendered text and native undo."""

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-search-") as temporary:
        folder = Path(temporary)
        path = folder / "search.md"
        original = (
            "# Search\n\nİ 😀 Cat cat CAT cats\n\nhello **world** end\n\nnext paragraph\n\n"
            "سلام سلامتی (سلام) سلام\u200cها\n\n[link](https://example.com/source-only)\n"
        )
        path.write_text(original)
        other = folder / "other.html"
        other.write_text(
            "<p>other <em>document</em></p><div>alpha</div><div>beta</div><p>line<br>break</p>"
            "<p>collapsed\n  <em>  white</em>   space&nbsp;works</p>"
        )
        window = ReaderWindow([path, other], settings_path=folder / "settings.ini")
        window.resize(1280, 900)
        window.show()
        field = "document.querySelector('.source-editor:not([hidden])')"

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script[:200]
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(40)
            count = evaluate("document.getElementById('search-count').textContent")
            raise AssertionError(f"{label}; errors: {errors}; count: {count}")

        def click(identifier):
            evaluate(f"document.getElementById({json.dumps(identifier)}).click()")

        def key(value, modifiers=Qt.KeyboardModifier.NoModifier):
            QTest.keyClick(window.view.focusProxy() or window.view, value, modifiers)
            QTest.qWait(100)

        def query(value, expected=None):
            evaluate(
                f"document.getElementById('search-input').value={json.dumps(value)}; readerApp.search()"
            )
            if expected is not None:
                count = evaluate("document.getElementById('search-count').textContent")
                assert count == expected, (value, count, expected, errors)

        def write(value):
            evaluate(
                f"(() => {{ const e={field}; e.value={json.dumps(value)}; e.setSelectionRange(0,0); e.dispatchEvent(new Event('input', {{bubbles:true}})); }})()"
            )

        def source():
            return evaluate(f"{field}.value")

        def replacement(value):
            evaluate(f"document.getElementById('replace-input').value={json.dumps(value)}")

        def selected():
            return evaluate(
                f"(() => {{ const e={field}; return e.value.slice(e.selectionStart,e.selectionEnd); }})()"
            )

        try:
            wait(
                "!!window.readerApp?.activeId && document.querySelectorAll('.file-item').length===2",
                "documents loaded",
            )
            evaluate(
                "[...document.querySelectorAll('.file-item')].find(e=>e.textContent.includes('search.md')).querySelector('button').click()"
            )
            first_id = evaluate("readerApp.activeId")
            click("search-button")
            assert evaluate(
                "document.getElementById('replace-controls').hidden && document.getElementById('search-toggle-replace').getAttribute('aria-expanded')==='false'"
            )
            assert evaluate(
                "['search-case','search-word'].every(id=>document.getElementById(id).matches('button[aria-pressed=\"false\"]'))"
            )
            assert evaluate(
                "(()=>{const input=document.getElementById('search-input').getBoundingClientRect();return ['search-case','search-word'].every(id=>{const r=document.getElementById(id).getBoundingClientRect();return r.left>=input.right && Math.abs(r.top+r.height/2-input.top-input.height/2)<2})})()"
            )
            query("hello world", "1 of 1")
            assert evaluate(
                "[...CSS.highlights.get('reader-search')][0].toString()==='hello world'"
            )
            query("cat", "1 of 4")
            click("search-next")
            assert evaluate("document.getElementById('search-count').textContent==='2 of 4'")
            click("search-case")
            assert evaluate("document.getElementById('search-count').textContent.endsWith('of 2')")
            click("search-word")
            query("cat", "1 of 1")
            assert evaluate("[...CSS.highlights.get('reader-current')][0].toString()==='cat'")
            click("search-case")
            query("سلام", "1 of 2")
            click("search-word")
            query("endnext", "No matches")
            query("source-only", "No matches")
            assert evaluate("document.getElementById('search-replace-all').disabled")
            print(
                "PASS: reading search spans inline markup, preserves Unicode offsets and respects options",
                flush=True,
            )

            click("edit-mode")
            click("search-toggle-replace")
            assert evaluate(
                "!document.getElementById('replace-controls').hidden && document.getElementById('search-toggle-replace').getAttribute('aria-expanded')==='true' && document.activeElement.id==='replace-input'"
            )
            click("search-toggle-replace")
            assert evaluate(
                "document.getElementById('replace-controls').hidden && document.activeElement.id==='search-input'"
            )
            click("search-toggle-replace")
            query("source-only", "1 of 1")
            assert selected() == "source-only"
            assert evaluate("!document.getElementById('search-replace-all').disabled")
            write("fresh-only CAT cat cat")
            query("fresh-only", "1 of 1")
            assert selected() == "fresh-only"
            query("cat", "1 of 3")
            click("search-next")
            assert selected() == "cat"
            wait(
                "document.getElementById('document').textContent.includes('fresh-only')",
                "fresh preview arrives",
            )
            assert evaluate("document.getElementById('search-count').textContent==='2 of 3'")
            assert evaluate(f"{field}.selectionStart===15")
            evaluate(
                f"{field}.focus(); {field}.setSelectionRange({field}.value.length, {field}.value.length)"
            )
            QTest.keyClicks(window.view.focusProxy() or window.view, " ")
            QTest.qWait(250)
            assert evaluate(f"{field}.selectionStart==={field}.value.length")
            print(
                "PASS: editing search uses unsaved source and keeps selection across preview updates",
                flush=True,
            )

            # Enter before the query debounce fires must select the new query's first match.
            evaluate(
                "document.getElementById('search-input').value='fresh-only'; document.getElementById('search-input').dispatchEvent(new Event('input')); document.getElementById('search-input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))"
            )
            assert selected() == "fresh-only"
            query("cat", "1 of 3")
            click("search-prev")
            assert evaluate("document.getElementById('search-count').textContent==='3 of 3'")
            evaluate("document.getElementById('search-input').focus()")
            key(Qt.Key.Key_F3)
            assert evaluate("document.getElementById('search-count').textContent==='1 of 3'")
            key(Qt.Key.Key_F3, Qt.KeyboardModifier.ShiftModifier)
            assert evaluate("document.getElementById('search-count').textContent==='3 of 3'")
            print("PASS: immediate Enter, previous/next and F3 wrap correctly", flush=True)

            write("cat cat cats")
            query("cat")
            click("search-word")
            replacement("$&\\x")
            click("search-replace")
            assert source() == "$&\\x cat cats", source()
            assert selected() == "cat"
            evaluate(f"{field}.focus()")
            key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            assert source() == "cat cat cats", source()
            replacement("catcat")
            click("search-replace-all")
            assert source() == "catcat catcat cats", source()
            evaluate(f"{field}.focus()")
            key(Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            assert source() == "cat cat cats", source()
            key(
                Qt.Key.Key_Z,
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            )
            assert source() == "catcat catcat cats", source()
            print(
                "PASS: literal Replace and Replace All are single undoable edits with redo",
                flush=True,
            )

            write("cat cat")
            query("cat")
            replacement("")
            click("search-replace-all")
            assert source() == " "
            # A queued search must never replace offsets from the previous buffer.
            write("x cat")
            query("cat")
            evaluate(
                f"(() => {{const e={field}; e.value='prefix cat suffix'; e.dispatchEvent(new Event('input', {{bubbles:true}})); document.getElementById('replace-input').value='dog'; document.getElementById('search-replace-all').click();}})()"
            )
            assert source() == "prefix dog suffix"
            click("save-button")
            wait(
                "document.getElementById('save-status').textContent==='Saved'",
                "replacement saves through the native file bridge",
            )
            assert path.read_text() == "prefix dog suffix"
            print(
                "PASS: empty replacements and edits immediately before replacement use current source",
                flush=True,
            )

            write("cat\n" * 2105)
            query("cat", "1 of 2,105")
            click("search-prev")
            assert evaluate(f"{field}.selectionStart===8416")
            wait(f"{field}.scrollTop>1000", "last result beyond 2000 scrolls into view")
            assert evaluate(
                "(()=>{const r=[...CSS.highlights.get('reader-source-current')][0].getBoundingClientRect(),v=document.querySelector('.source-editor:not([hidden])').getBoundingClientRect();return r.top>=v.top && r.bottom<=v.bottom})()"
            )
            click("search-all")
            assert evaluate(
                "document.getElementById('search-results-dialog').open && document.querySelectorAll('.search-result').length===100 && !document.getElementById('search-panel').contains(document.getElementById('search-results'))"
            )
            (ROOT / "artifacts").mkdir(exist_ok=True)
            QTest.qWait(200)
            window.grab().save(str(ROOT / "artifacts/search-results-dialog.png"))
            evaluate(
                "document.querySelector('.search-more').click(); document.querySelector('.search-result[data-index=\"102\"]').click()"
            )
            assert evaluate(f"{field}.selectionStart===408")
            assert evaluate(
                f"!document.getElementById('search-results-dialog').open && document.activeElement==={field}"
            )
            click("search-all")
            key(Qt.Key.Key_Escape)
            assert evaluate(
                "!document.getElementById('search-results-dialog').open && !document.getElementById('search-panel').hidden"
            )
            replacement("dog")
            click("search-replace-all")
            assert source() == "dog\n" * 2105
            print(
                "PASS: Find All lists every match progressively and Replace All has no 2000-match limit",
                flush=True,
            )

            write("one " * 400 + "wrapped-target " + "فارسی " * 100)
            query("wrapped-target", "1 of 1")
            QTest.qWait(200)
            assert evaluate(
                "(()=>{const r=[...CSS.highlights.get('reader-source-current')][0].getBoundingClientRect(),v=document.querySelector('.source-editor:not([hidden])').getBoundingClientRect();return r.top>=v.top && r.bottom<=v.bottom})()"
            )
            print(
                "PASS: wrapped source match is visible without relying on source-line estimates",
                flush=True,
            )
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts/search-source.png"))

            click("search-close")
            assert evaluate(
                f"document.activeElement==={field} && !CSS.highlights.has('reader-source-search')"
            )
            evaluate(f"{field}.setSelectionRange(0,3)")
            key(Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
            assert evaluate("document.getElementById('search-input').value==='one'")
            assert evaluate("document.getElementById('replace-controls').hidden")
            click("read-mode")
            key(Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
            assert evaluate(
                "document.body.classList.contains('editing') && document.activeElement.id==='replace-input' && !document.getElementById('replace-controls').hidden"
            )
            key(Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
            assert evaluate(
                "document.getElementById('replace-controls').hidden && document.activeElement.id==='search-input'"
            )
            print(
                "PASS: Ctrl+F uses selected source and Ctrl+H opens replacement in editing mode",
                flush=True,
            )

            evaluate(
                "[...document.querySelectorAll('.file-item')].find(e=>e.textContent.includes('other.html')).querySelector('button').click()"
            )
            query("other document", "1 of 1")
            assert evaluate("document.getElementById('replace-input').disabled")
            click("search-word")
            query("alphabeta", "No matches")
            query("linebreak", "No matches")
            query("collapsed white space works", "1 of 1")
            evaluate(
                "const hidden=document.createElement('p'); hidden.hidden=true; hidden.textContent='hidden-needle'; document.getElementById('document').append(hidden)"
            )
            query("hidden-needle", "No matches")
            evaluate(
                "const details=document.createElement('details'); details.innerHTML='<summary>expand-me</summary>collapsed-needle<p>closed-paragraph</p>'; document.getElementById('document').append(details)"
            )
            query("expand-me", "1 of 1")
            query("collapsed-needle", "No matches")
            query("closed-paragraph", "No matches")
            evaluate("document.querySelector('#document details').open=true")
            query("collapsed-needle", "1 of 1")
            query("other", "1 of 1")
            click("search-all")
            evaluate("document.querySelector('.search-result').click()")
            assert evaluate(
                "!document.getElementById('search-results-dialog').open && document.activeElement.id==='document' && [...CSS.highlights.get('reader-current')][0].toString()==='other'"
            )
            click("search-all")
            click("search-results-close")
            assert evaluate("!document.getElementById('search-results-dialog').open")
            window.grab().save(str(ROOT / "artifacts/search-reading.png"))
            evaluate(f"readerApp.showDocument({json.dumps(first_id)})")
            query("other", "No matches")
            print(
                "PASS: tab/mode switching rebuilds scope, hidden text and block boundaries are excluded",
                flush=True,
            )
            evaluate("readerApp.command('empty')")
            assert evaluate(
                "document.getElementById('search-replace-all').disabled && !CSS.highlights.has('reader-source-current')"
            )
            assert not errors, errors
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(100)


if __name__ == "__main__":
    main()
