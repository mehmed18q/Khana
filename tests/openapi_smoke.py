"""Exercise offline Swagger rendering, editing, source fallback and reader integration."""
from pathlib import Path
import json
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication
from reader.desktop import ReaderPage, ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    errors = []
    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(message)
    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix='khana-openapi-') as tmp:
        folder = Path(tmp)
        source = 'openapi: 3.0.3\ninfo:\n  title: Khana Example API\n  version: "1.0"\n  description: توضیحات فارسی برای API\npaths:\n'
        for number in range(24):
            source += f'''  /items/{number}:
    get:
      summary: خواندن مورد {number}
      parameters:
        - name: limit
          in: query
          schema: {{type: integer}}
      responses:
        200:
          description: Success
          content:
            application/json:
              schema: {{$ref: '#/components/schemas/Item'}}
'''
        source += 'components:\n  schemas:\n    Item:\n      type: object\n      properties:\n        title: {type: string}\n'
        yaml = folder / 'api.yaml'; yaml.write_text(source)
        window = ReaderWindow(settings_path=folder / 'settings.ini'); window.showFullScreen()
        shadow = "document.querySelector('.swagger-host')?.shadowRoot"
        field = "document.querySelector('.source-editor:not([hidden])')"
        def evaluate(script):
            values = []; window.page.runJavaScript(script, lambda result: values.append(result))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline: QTest.qWait(20)
            assert values, script[:100]
            return values[0]
        def wait(script, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if evaluate(script): print('PASS:', label, flush=True); return
                QTest.qWait(50)
            raise AssertionError(f'{label}: {errors}; ' + str(evaluate("document.getElementById('toast').textContent")))
        def click(identifier): evaluate(f"document.getElementById('{identifier}').click()")
        def edit(text):
            evaluate(field + '.value=' + json.dumps(text) + ';' + field + ".dispatchEvent(new Event('input',{bubbles:true}))")
        try:
            wait('!!window.readerApp?.activeId', 'desktop loads')
            window.bridge.load_paths([yaml])
            wait(shadow + "?.querySelectorAll('[data-api-operation]').length===24", 'YAML opens in Swagger UI')
            assert evaluate(shadow + ".querySelector('.info .title').textContent.includes('Khana Example API')")
            assert evaluate(shadow + ".querySelector('.info .description p').dir==='rtl'")
            assert evaluate("document.querySelectorAll('#outline button').length===24")
            evaluate(shadow + ".querySelector('.opblock-summary-control').click()")
            wait(shadow + ".querySelectorAll('.responses-table').length>0", 'expand parameters and responses')
            assert evaluate("!!" + shadow + ".querySelector('.try-out__btn')")
            assert evaluate(shadow + ".querySelector('.responses-table').textContent.includes('200')")
            assert not evaluate(shadow + ".querySelector('.errors-wrapper')")
            click('theme-button')
            assert evaluate("document.querySelector('.swagger-host').dataset.theme==='dark'")
            click('theme-button')
            click('preview-zoom-in')
            assert evaluate("document.getElementById('preview-zoom-value').textContent==='110%'")
            assert window.view.zoomFactor() == 1
            click('preview-zoom-reset')
            # Marks use stable method/path anchors even after opening a response.
            click('add-note')
            wait("document.getElementById('annotation-dialog').open", 'add a note to an API operation')
            evaluate("document.getElementById('annotation-body').value='Review this endpoint';document.getElementById('annotation-save').click()")
            wait(shadow + ".querySelectorAll('.annotation-badge.note').length===1", 'API note saved')
            click('api-preview-source')
            wait("!!document.querySelector('.structured-source') && !document.querySelector('.swagger-host')", 'switch to literal source')
            click('api-preview-swagger')
            wait(shadow + "?.querySelectorAll('.annotation-badge.note').length===1", 'API note restored')
            click('edit-mode')
            wait(field + ' !== null', 'source editor remains available')
            assert evaluate("document.getElementById('format-toolbar').hidden && !document.getElementById('beautify-button').hidden")
            evaluate(field + '.scrollTop=' + field + '.scrollHeight')
            wait("document.getElementById('reading-scroll').scrollTop>500", 'editor scroll moves Swagger preview')
            evaluate("document.getElementById('reading-scroll').scrollTo({top:0,behavior:'instant'})")
            wait(field + '.scrollTop<5', 'Swagger scroll moves editor')
            evaluate(shadow + ".querySelector('[data-api-operation=\"GET /items/12\"]').scrollIntoView({block:'start',behavior:'instant'})")
            wait(field + '.scrollTop>2000', 'endpoint source mapping works in the middle of the document')
            evaluate('(()=>{const field=' + field + ";field.focus();const offset=field.value.indexOf('خواندن مورد 12');field.setSelectionRange(offset,offset+'خواندن مورد 12'.length);document.execCommand('insertText',false,'Updated item twelve')})()")
            wait(shadow + "?.querySelector('[data-api-operation=\"GET /items/12\"]')?.textContent.includes('Updated item twelve')", 'edit the currently visible endpoint')
            QTest.qWait(300)
            assert evaluate(field + '.scrollTop>2000'), 'live Swagger rendering must retain the source scroll position'
            edit(source.replace('Khana Example API', 'Updated API'))
            wait(shadow + "?.querySelector('.info .title')?.textContent.includes('Updated API')", 'live Swagger preview updates')
            edit('openapi: [broken')
            wait("document.getElementById('api-preview-controls').hidden && !!document.querySelector('.structured-source')", 'invalid edits fall back to readable source')
            edit(source)
            wait(shadow + "?.querySelectorAll('[data-api-operation]').length===24", 'valid edits restore Swagger')
            # Runtime should not request the online validator or API server.
            assert evaluate("performance.getEntriesByType('resource').every(item=>!/^https?:/.test(item.name))")
            ordinary = folder / 'ordinary.json'; ordinary.write_text('{"hello":"world"}')
            window.bridge.load_paths([ordinary])
            wait('readerApp.activeId===' + json.dumps(str(ordinary)), 'open ordinary JSON')
            assert evaluate("document.getElementById('api-preview-controls').hidden && !!document.querySelector('.structured-source')")
            for key, version in [('swagger', '2.0'), ('openapi', '3.1.1'), ('openapi', '3.2.0')]:
                path = folder / f'{key}-{version}.json'
                path.write_text(json.dumps({key: version, 'info': {'title': version + ' API', 'version': '1'},
                    'paths': {'/hello': {'get': {'responses': {'200': {'description': 'Hello'}}}}}}))
                window.bridge.load_paths([path])
                wait(shadow + "?.querySelector('.info .title')?.textContent.includes(" + json.dumps(version + ' API') + ")", f'{key} {version} JSON preview')
                wait(shadow + "?.querySelectorAll('[data-api-operation]').length===1", 'JSON operation source mapping')
            window.bridge.load_paths([yaml])
            wait(shadow + "?.querySelectorAll('[data-api-operation]').length===24", 'return to YAML')
            click('read-mode')
            evaluate(shadow + ".querySelector('.opblock-summary-control').click()")
            QTest.qWait(300)
            (ROOT / 'artifacts').mkdir(exist_ok=True)
            window.grab().save(str(ROOT / 'artifacts' / 'openapi-preview.png'))
            assert not errors, errors
            print('OpenAPI smoke test passed.', flush=True)
        finally:
            window.allow_close = True; window.close(); window.page.deleteLater(); QTest.qWait(100)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
