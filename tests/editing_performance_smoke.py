"""Exercise selection, context menus and undo in small and large source buffers."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --disable-gpu"
    ).strip()

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from reader.ui.window import ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="khana-editing-") as temporary:
        folder = Path(temporary)
        paths = []
        for name, count in (("small", 20), ("large", 3000)):
            path = folder / f"{name}.md"
            path.write_text(
                "# Document\n\n"
                + "\n\n".join(f"hello helllo سلام سللام English text {i}" for i in range(count)),
                encoding="utf-8",
            )
            paths.append(path)
        window = ReaderWindow([paths[0]], settings_path=folder / "settings.ini")
        window.resize(1320, 900)
        window.show()

        def js(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 30
            while not values and time.monotonic() < deadline:
                QTest.qWait(10)
            assert values, script
            return values[0]

        def wait(script):
            deadline = time.monotonic() + 60
            while not js(script):
                assert time.monotonic() < deadline, (
                    script,
                    js("document.getElementById('toast').textContent"),
                    window.bridge.initialized,
                    list(window.bridge.jobs.loads),
                )
                QTest.qWait(30)

        def measure(label, script):
            js(
                "window.editTiming=null;(()=>{const start=window.editStarted=performance.now();"
                + script
                + ";const handler=performance.now()-start;requestAnimationFrame(()=>"
                "requestAnimationFrame(()=>window.editTiming={handler,paint:performance.now()-start}))})()"
            )
            wait("window.editTiming!==null")
            result = json.loads(js("JSON.stringify(window.editTiming)"))
            print(label, json.dumps(result), flush=True)
            # Catch the original multi-second stalls while tolerating slower CI hosts.
            assert result["handler"] < 350, (label, result)
            assert result["paint"] < 1500, (label, result)
            return result

        def selection_visible():
            assert js("""(()=>{const ranges=CSS.highlights.get('reader-editor-selection');
              if(!ranges || ranges.size!==1)return false;
              const r=[...ranges][0], b=r.getBoundingClientRect();
              return r.toString()===field.value.slice(field.selectionStart,field.selectionEnd)
                && b.width>0 && b.height>0 && !document.querySelector('.spelling-layer').hidden
                && !!document.activeElement.closest('#file-context-menu');})()""")

        results = {}
        try:
            for path in paths:
                if path != paths[0]:
                    window.bridge.load_paths([path])
                wait(
                    f"window.readerApp?.activeId?.endsWith({json.dumps(path.name)}) && document.fonts.status==='loaded'"
                )
                js("readerApp.setEditMode(true)")
                wait("CSS.highlights.get('reader-spelling')?.size>1")
                assert js("CSS.highlights.get('reader-spelling').size<200"), (
                    "Offscreen spelling ranges should not slow caret changes"
                )
                QTest.qWait(200)
                js("""window.field=document.querySelector('.source-editor:not([hidden])');
                  window.openEditMenu=()=>{
                    const r=new Range(),m=document.querySelector('.spelling-text');
                    r.setStart(m.firstChild,field.selectionStart);r.setEnd(m.firstChild,field.selectionEnd);
                    const b=r.getBoundingClientRect();
                    field.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,
                      clientX:b.x+b.width/2,clientY:b.y+b.height/2}));
                  };window.original=field.value;field.focus();field.setSelectionRange(18,24);field.scrollTop=0;""")
                QTest.qWait(100)
                result = results[path.stem] = {}
                result["menu"] = measure("menu " + path.stem, "openEditMenu()")
                selection_visible()
                (ROOT / "artifacts").mkdir(exist_ok=True)
                window.grab().save(str(ROOT / "artifacts" / "editor-selection.png"))
                result["copy"] = measure(
                    "copy " + path.stem, "document.querySelector('[data-action=copy]').click()"
                )
                wait("document.getElementById('file-context-menu').hidden")
                assert window.bridge.clipboardText() == js("original.slice(18,24)")
                assert js("!CSS.highlights.has('reader-editor-selection')")
                result["typing"] = measure(
                    "typing " + path.stem,
                    "field.focus();document.execCommand('insertText',false,'changed')",
                )
                assert js("field.value===original.slice(0,18)+'changed'+original.slice(24)")
                result["undo"] = measure("undo " + path.stem, "document.execCommand('undo')")
                assert js("field.value===original")
                result["redo"] = measure("redo " + path.stem, "document.execCommand('redo')")
                assert js("field.value===original.slice(0,18)+'changed'+original.slice(24)")
                measure("restore " + path.stem, "document.execCommand('undo')")
                wait("document.getElementById('preview-status').textContent==='Live preview'")
                wait("CSS.highlights.get('reader-spelling')?.size>1")
                js("field.setSelectionRange(18,24)")
                result["menu_again"] = measure("menu again " + path.stem, "openEditMenu()")
                js("document.querySelector('[data-action=copy]').click()")
                js(
                    "document.getElementById('spellcheck-button').click();field.setSelectionRange(18,24)"
                )
                measure("menu without spelling " + path.stem, "openEditMenu()")
                selection_visible()
                js("document.querySelector('[data-action=cut]').click()")
                assert js("field.value===original.slice(0,18)+original.slice(24)")
                js("openEditMenu();document.querySelector('[data-action=undo]').click()")
                assert js("field.value===original")
                js("openEditMenu();document.querySelector('[data-action=redo]').click()")
                assert js("field.value===original.slice(0,18)+original.slice(24)")
                js("field.focus();document.execCommand('undo')")
                assert js("field.value===original")
                js("document.getElementById('spellcheck-button').click()")
            print(json.dumps(results, indent=2), flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0 if app else 1


if __name__ == "__main__":
    raise SystemExit(main())
