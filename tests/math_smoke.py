"""Render the Persian Fourier example in real WebEngine, including live edits and panes."""

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
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-math-") as temporary:
        folder = Path(temporary)
        path, other = folder / "ریاضی.md", folder / "second.md"
        source = (ROOT / "examples/math-and-persian.md").read_text()
        path.write_text(source)
        other.write_text("# Other document\n\nمتن کنار $a_b+a_c$.\n\n$$\\sqrt{x^2+1}$$")
        window = ReaderWindow([other, path], settings_path=folder / "settings.ini")
        window.resize(1320, 1000)
        window.show()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script
            return values[0]

        def wait(script):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    return
                QTest.qWait(40)
            raise AssertionError(f"{script}: {errors}")

        def click(identifier):
            evaluate(f"document.getElementById({json.dumps(identifier)}).click()")

        def edit(value):
            evaluate(
                "(()=>{const e=document.querySelector('.source-editor:not([hidden])');e.value="
                + json.dumps(value)
                + ";e.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )

        try:
            wait("!!window.readerApp && document.querySelectorAll('.file-item').length===2")
            evaluate(f"readerApp.showDocument({json.dumps(str(path))})")
            wait(
                "document.querySelectorAll('#document .katex').length===15 && document.fonts.status==='loaded'"
            )
            assert evaluate("!document.querySelector('#document .math-error')")
            assert evaluate("document.querySelectorAll('#document .katex-display').length===6")
            assert evaluate("document.querySelectorAll('#document math').length===15")
            assert evaluate("document.querySelectorAll('#document .mfrac').length>=10")
            assert evaluate("document.fonts.check('20px KaTeX_Main')")
            assert evaluate("!document.querySelector('.math-expression bdi')")
            assert evaluate(
                "[...document.querySelectorAll('#document .math-display > .math-render')].every(e=>e.scrollWidth<=e.clientWidth+1)"
            )
            assert evaluate(
                "[...document.querySelectorAll('#document p')].filter(p=>p.querySelector('.math-expression')).every(p=>p.dir==='rtl')"
            )
            original_math = evaluate(
                "JSON.stringify([...document.querySelectorAll('#document .math-expression')].map(e=>e.dataset.mathSource))"
            )
            for mode in ("rtl", "ltr", "smart"):
                evaluate(f"document.querySelector('[data-direction={mode}]').click()")
                assert evaluate(
                    "[...document.querySelectorAll('#document .math-expression')].every(e=>getComputedStyle(e).direction==='ltr')"
                )
                assert (
                    evaluate(
                        "JSON.stringify([...document.querySelectorAll('#document .math-expression')].map(e=>e.dataset.mathSource))"
                    )
                    == original_math
                )
            QTest.qWait(200)
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts" / "math-persian-light.png"))
            print(
                "PASS: all 15 formulas render with local fonts, fractions and MathML; Persian prose and math keep independent directions",
                flush=True,
            )

            click("theme-button")
            evaluate(
                "document.getElementById('reading-scroll').scrollTo({top:100000,behavior:'instant'})"
            )
            QTest.qWait(200)
            window.grab().save(str(ROOT / "artifacts" / "math-persian-dark.png"))
            click("edit-mode")
            assert (
                evaluate("document.querySelector('.source-editor:not([hidden])').value") == source
            )
            edit(source.replace(r"\boxed{\pi^2-x^2=", r"\boxed{y="))
            wait(
                "[...document.querySelectorAll('#document .math-expression')].some(e=>e.dataset.mathSource.startsWith('\\\\boxed{y='))"
            )
            assert evaluate("document.querySelectorAll('#document .katex').length===15")
            assert path.read_text() == source
            print(
                "PASS: live preview updates formulas without changing the saved file or editor source",
                flush=True,
            )

            click("read-mode")
            evaluate(
                "(()=>{const s=document.getElementById('reading-layout');s.value='columns';s.dispatchEvent(new Event('change'));})()"
            )
            wait("document.querySelectorAll('.extra-pane .katex').length===2")
            assert evaluate("!document.querySelector('.extra-pane .math-expression bdi')")
            window.resize(860, 600)
            QTest.qWait(200)
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            assert evaluate(
                "[...document.querySelectorAll('.math-display')].every(e=>e.getBoundingClientRect().width<=e.closest('.document').clientWidth)"
            )
            print(
                "PASS: split panes render math and narrow windows retain horizontal containment",
                flush=True,
            )

            click("edit-mode")
            invalid = (
                source
                + "\n\n$\\notARealCommand{x}$\n\n$\\href{javascript:alert(1)}{x}$\n\n`$not_math$`\n\n$$x=3$$\n\n$\\text{NeedleMath}$\n"
            )
            edit(invalid)
            wait(
                "document.querySelector('#document .math-error')!==null && document.querySelectorAll('#document .katex').length===18"
            )
            assert evaluate(
                "!document.querySelector('#document .math-expression a, #document .math-expression script')"
            )
            assert evaluate("document.querySelector('#document code').textContent==='$not_math$'")
            assert evaluate(
                "document.querySelector('#document .math-error').textContent==='\\\\notARealCommand{x}'"
            )
            click("read-mode")
            click("search-button")
            evaluate(
                "document.getElementById('search-input').value='NeedleMath';readerApp.search()"
            )
            assert evaluate("document.getElementById('search-count').textContent==='1 of 1'")
            assert evaluate("[...CSS.highlights.get('reader-search')][0].toString()==='NeedleMath'")
            assert not errors, errors
            print(
                "PASS: invalid formulas remain readable, later formulas render, code stays literal and untrusted links stay inactive",
                flush=True,
            )
            print("Math smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
            window.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
