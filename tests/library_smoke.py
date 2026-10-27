"""Real window restarts exercise persistent libraries, multiple marks and notes."""
from pathlib import Path
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication
from reader.desktop import ReaderPage, ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []
    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f'{source}:{line}: {message}')
    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix='khana-library-') as temporary:
        folder = Path(temporary); settings = folder / 'settings.ini'
        md = folder / 'مطالعه.md'; html = folder / 'reference.html'
        original = '# Reading project\n\n' + '\n\n'.join(f'Paragraph {i}: این بخش از سند برای مطالعهٔ فارسی و English است. Keep reading carefully.' for i in range(1, 81))
        md.write_text(original)
        html.write_text('<h1>HTML reference</h1><p>یادداشت روی فایل HTML هم ذخیره می‌شود.</p><table><tr><th>Title</th></tr><tr><td>Value</td></tr></table>')
        window = None
        def evaluate(script):
            values = []; window.page.runJavaScript(script, lambda value: values.append(value))
            deadline = time.monotonic() + 8
            while not values and time.monotonic() < deadline: QTest.qWait(20)
            assert values, script[:100]
            return values[0]
        def wait(script, label):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if evaluate(script): print('PASS:', label, flush=True); return
                QTest.qWait(50)
            raise AssertionError(f'{label}: {errors}; toast=' + str(evaluate("document.getElementById('toast').textContent")))
        def click(name): evaluate(f"document.getElementById('{name}').click()")
        def launch(paths=()):
            nonlocal window
            window = ReaderWindow(paths, settings_path=settings); window.showFullScreen()
            wait("!!window.readerApp && document.getElementById('library-list').children.length>0", 'library shell loads')
        def close():
            nonlocal window
            window.close(); QTest.qWait(180)
            assert not window.isVisible(), 'Closing should not need to save an annotated document'
            window.page.deleteLater(); QTest.qWait(80)
            # Destroy each profile/window after its page, before simulating a
            # restart. Leaving closed windows for Python GC races WebEngine.
            window.deleteLater(); QTest.qWait(80); window = None
        def add(kind, index, name, body=''):
            button = 2 if kind == 'note' else 1
            evaluate(f"document.querySelector('[data-reading-block=\"{index}\"] > .annotation-tools button:nth-child({button})').click()")
            assert evaluate("document.getElementById('annotation-dialog').open")
            evaluate('document.getElementById("annotation-name").value=' + json.dumps(name))
            evaluate('document.getElementById("annotation-body").value=' + json.dumps(body))
            click('annotation-save')
            wait("!document.getElementById('annotation-dialog').open", f'{kind} saved: {name}')
        def visible_paragraph(number):
            return "(() => {const p=[...document.querySelectorAll('#document p')].find(p=>p.textContent.startsWith('Paragraph " + str(number) + ":'));const r=p.getBoundingClientRect(),s=document.getElementById('reading-scroll').getBoundingClientRect();return r.top>=s.top-5 && r.top<s.bottom;})()"
        try:
            launch([md]); wait("document.querySelectorAll('#document p').length===80", 'long mixed-language document loads')
            evaluate("document.getElementById('document').focus()")
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
            wait("document.getElementById('annotation-dialog').open && document.getElementById('annotation-dialog-title').textContent==='Add mark'", 'Ctrl+M opens a reading mark')
            click('annotation-cancel'); QTest.qWait(60)
            QTest.keyClick(window.view.focusProxy() or window.view, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            wait("document.getElementById('annotation-dialog').open && document.getElementById('annotation-dialog-title').textContent==='Add note'", 'Ctrl+Shift+M opens a note')
            click('annotation-cancel'); QTest.qWait(60)
            click('star-document')
            wait("document.getElementById('star-document').getAttribute('aria-pressed')==='true'", 'document is starred')
            add('mark', 20, 'First checkpoint')
            add('mark', 60, 'Later chapter')
            # Select actual text before using the toolbar's Add note action.
            evaluate("(() => {const p=document.querySelector('[data-reading-block=\"40\"]');const range=document.createRange();range.selectNodeContents(p);const s=getSelection();s.removeAllRanges();s.addRange(range);})()")
            click('add-note')
            evaluate("document.getElementById('annotation-name').value='نظر من'")
            evaluate('document.getElementById("annotation-body").value=' + json.dumps('یادداشت فارسی با English\n<script>literal text</script>'))
            click('annotation-save')
            wait("document.getElementById('annotation-count').textContent==='3'", 'multiple marks and selected-text note coexist')
            record = window.bridge.library.get(str(md))
            first, later, note = record['annotations']
            assert note['anchor']['quote'].startswith('Paragraph 40:')
            assert md.read_text() == original
            assert evaluate("document.getElementById('save-status').textContent==='Saved'")
            assert evaluate("document.querySelectorAll('.annotation-badge').length===3")
            assert evaluate("document.querySelector('.developer-credit').textContent==='© 2026 · Development by Sadeq Kiomarsi'")
            click('annotations-button')
            evaluate('document.querySelector(' + json.dumps(f'[data-id="{first["id"]}"] .annotation-jump') + ').click()')
            wait(visible_paragraph(20), 'jump to a chosen mark')
            window.bridge.load_paths([html]); wait("readerApp.activeId.endsWith('reference.html')", 'HTML opens alongside Markdown')
            add('note', 2, 'Table note', 'A note on the table.')
            assert evaluate("document.querySelector('.table-scroll > .annotation-badges .annotation-badge')!==null")
            assert evaluate("document.querySelector('#document table').textContent==='TitleValue'")
            click('annotations-button')
            evaluate("document.querySelector('.annotation-actions button:last-child').click()")
            wait("document.getElementById('annotation-count').textContent==='0'", 'table note has a visible badge and can be deleted')
            add('note', 1, 'HTML note', 'Remember this reference.')
            click('star-document')
            evaluate("readerApp.command('close')")
            wait("document.getElementById('file-count').textContent==='1'", 'closed document stays in library')
            close()

            # Text inserted above the mark must not move its meaning to a different paragraph.
            md.write_text('# Inserted heading\n\nAn inserted paragraph.\n\n' + original)
            launch(); wait("readerApp.activeId?.endsWith('مطالعه.md')", 'last open saved document is restored after restart')
            wait("document.getElementById('annotation-count').textContent==='3'", 'all marks and notes survive restart')
            wait(visible_paragraph(20), 'resume finds the same paragraph after preceding text is inserted')
            click('library-starred')
            assert evaluate("document.querySelectorAll('.library-item').length===2")
            assert evaluate("document.querySelectorAll('.file-item').length===1")
            click('annotations-button')
            assert evaluate("document.querySelector('.annotation-note').textContent.includes('<script>literal text</script>')")
            assert not evaluate("document.querySelector('.annotation-note script')!==null")
            evaluate('document.querySelector(' + json.dumps(f'[data-id="{note["id"]}"] .annotation-actions button') + ').click()')
            evaluate("document.getElementById('annotation-name').value='Updated note'; document.getElementById('annotation-body').value='Edited safely.'")
            click('annotation-save'); wait("!document.getElementById('annotation-dialog').open", 'note name and body can be edited')
            click('annotations-button')
            artifacts = ROOT / 'artifacts'; artifacts.mkdir(exist_ok=True)
            window.grab().save(str(artifacts / 'library-light.png'))
            click('theme-button'); click('annotations-button'); QTest.qWait(100)
            window.grab().save(str(artifacts / 'library-dark.png'))
            for item in (later, note):
                evaluate('document.querySelector(' + json.dumps(f'[data-id="{item["id"]}"] .annotation-actions button:last-child') + ').click()')
                QTest.qWait(80)
            assert evaluate("document.getElementById('annotation-count').textContent==='1'")
            close()

            launch(); wait("document.getElementById('annotation-count').textContent==='1'", 'deleted marks and notes stay deleted after restart')
            assert window.bridge.library.get(str(md))['annotations'][0]['id'] == first['id']
            evaluate('document.querySelector(' + json.dumps(f'.library-item[data-path="{html}"] .library-open') + ').click()')
            wait("readerApp.activeId.endsWith('reference.html') && document.getElementById('annotation-count').textContent==='1'", 'starred closed document reopens with its own note')
            evaluate("readerApp.command('close')"); QTest.qWait(100)
            close(); md.unlink()
            launch(); wait('document.querySelector(' + json.dumps(f'.library-item[data-path="{md}"] .library-info') + ")?.textContent==='File not found'", 'missing file keeps its library entry and annotations')
            assert window.bridge.library.get(str(md))['annotations'][0]['id'] == first['id']
            md.write_text(original)
            evaluate('document.querySelector(' + json.dumps(f'.library-item[data-path="{md}"] .library-open') + ').click()')
            wait("readerApp.activeId?.endsWith('مطالعه.md')", 'restored source can be reopened from the retained library entry')
            click('new-file'); wait("readerApp.activeId.startsWith('untitled:')", 'new draft opens')
            assert evaluate("document.getElementById('add-mark').disabled && document.getElementById('add-note').disabled && document.getElementById('star-document').disabled")
            # Empty, unsaved drafts have no changes and can be closed without prompts.
            evaluate("readerApp.command('close')"); QTest.qWait(80)
            window.showNormal(); QTest.qWait(400); window.setFixedSize(900, 720)
            wait("innerWidth<=900", 'small viewport is active')
            if evaluate("document.getElementById('annotations-panel').hidden"):
                click('annotations-button')
            wait("!document.getElementById('annotations-panel').hidden && document.getElementById('annotations-panel').getBoundingClientRect().width>200", 'annotation list fits a small window')
            QTest.qWait(350)
            window.grab().save(str(artifacts / 'library-narrow.png'))
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            assert evaluate("document.getElementById('annotations-panel').getBoundingClientRect().right<=innerWidth")
            assert evaluate("document.getElementById('reading-scroll').clientHeight>100")
            assert not errors, errors
            close(); print('Library smoke test passed.', flush=True)
        finally:
            if window and window.isVisible():
                window.allow_close = True; window.close(); QTest.qWait(100)
                window.page.deleteLater(); QTest.qWait(80)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
