"""Check spellcheck markers against real textarea caret positions in WebEngine."""

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

from PySide6.QtCore import QPoint, Qt
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
    with tempfile.TemporaryDirectory(prefix="khana-spelling-") as temporary:
        folder = Path(temporary)
        path = folder / "spelling.md"
        source = (
            "hello helllo world\n"
            "سلام سللام کتاب\n"
            "hello سلام helllo سللام world کتاب\n"
            "سلام hello سللام helllo کتاب world\n\n"
            + ("hello world سلام کتاب " * 14 + "helllo سللام\n")
            * 30
        )
        path.write_text(source, encoding="utf-8")
        window = ReaderWindow([path], settings_path=folder / "settings.ini")
        window.resize(1320, 900)
        window.show()

        def js(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
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

        field = "document.querySelector('.source-editor:not([hidden])')"

        def check_markers(label):
            QTest.qWait(150)
            markers = json.loads(
                js(
                    """JSON.stringify((()=>{
                      const e=document.querySelector('.source-editor:not([hidden])'),
                        box=e.getBoundingClientRect(), hits=[];
                      for(const range of CSS.highlights.get('reader-spelling') || [])
                        for(const r of range.getClientRects())
                          if(r.top>box.top+25 && r.bottom<box.bottom-10 && r.width>2)
                            hits.push({start:range.startOffset,end:range.endOffset,
                              left:r.left+2,right:r.right-2,y:r.y+r.height/2,text:range.toString()});
                      return hits;
                    })())"""
                )
            )
            assert markers, label
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "spelling-markers.png"))
            for marker in markers[:8]:
                for edge in ("left", "right"):
                    QTest.mouseClick(
                        window.view.focusProxy() or window.view,
                        Qt.MouseButton.LeftButton,
                        pos=QPoint(round(marker[edge]), round(marker["y"])),
                    )
                    QTest.qWait(30)
                    actual = int(js(field + ".selectionStart"))
                    assert marker["start"] <= actual <= marker["end"], (
                        label,
                        marker,
                        edge,
                        actual,
                        source[max(0, actual - 15) : actual + 15],
                    )
            print("PASS:", label, flush=True)

        try:
            wait("!!window.readerApp?.activeId && document.fonts.status==='loaded'", "loaded")
            js("document.getElementById('edit-mode').click()")
            js("document.getElementById('sync-scroll').click()")
            wait("CSS.highlights.get('reader-spelling')?.size>8", "misspellings marked")
            check_markers("markers align with mixed-direction text")
            source = "سلام سللام کتاب\n" + source
            js(
                field
                + f".value={json.dumps(source)};"
                + field
                + ".dispatchEvent(new Event('input',{bubbles:true}))"
            )
            assert js("document.querySelector('.spelling-layer').hidden")
            wait("CSS.highlights.get('reader-spelling')?.size>8", "new source checked")
            check_markers("automatic RTL source moves the markers with the text viewport")
            for language in ("en", "fa"):
                js(
                    f"document.getElementById('ui-language').value='{language}';"
                    "document.getElementById('ui-language').dispatchEvent(new Event('change'))"
                )
                for direction in ("rtl", "ltr", "auto"):
                    js(
                        f"document.getElementById('editor-direction').value='{direction}';"
                        "document.getElementById('editor-direction').dispatchEvent(new Event('change'))"
                    )
                    wait("CSS.highlights.get('reader-spelling')?.size>8", "direction updated")
                    for top in (0, 1000):
                        js(field + f".scrollTop={top}")
                        check_markers(f"{language} UI, {direction} source, scroll {top}")
            window.resize(900, 700)
            QTest.qWait(300)
            js(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])'),"
                "r=[...CSS.highlights.get('reader-spelling')].find(r=>r.startOffset>200);"
                "e.scrollTop+=r.getBoundingClientRect().top-e.getBoundingClientRect().top-30})()"
            )
            check_markers("markers stay aligned after wrapping changes")
            assert not errors, errors
            print("Spelling geometry smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            QTest.qWait(150)
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
