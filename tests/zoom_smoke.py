"""Preview-only zoom through real Qt wheel/keyboard input and WebEngine layout."""

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pymupdf
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication

from reader.ui.web import ReaderPage
from reader.ui.window import ReaderWindow


def main():
    _app = QApplication.instance() or QApplication([])  # Keep Qt alive for the whole check.
    errors = []

    def console(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(message)

    ReaderPage.javaScriptConsoleMessage = console
    with tempfile.TemporaryDirectory(prefix="khana-zoom-") as temporary:
        folder = Path(temporary)
        photo = folder / "image.png"
        image = QImage(180, 100, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.green)
        image.save(str(photo))
        source = "\n\n".join(
            f"## Section {i}\n\nParagraph {i}: متن فارسی and English." for i in range(100)
        )
        source += (
            "\n\n![Photo]("
            + photo.as_uri()
            + ")\n\n| A | B |\n|---|---|\n| یک | Two |\n\n```mermaid\nflowchart TD\n A[Start] --> B[End]\n```\n"
        )
        path = folder / "long.md"
        path.write_text(source)
        settings = folder / "settings.ini"
        window = ReaderWindow([path], settings_path=settings)
        window.showFullScreen()

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda value: values.append(value))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script[:120]
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            raise AssertionError(f"{label}; {errors}")

        def click(identifier):
            evaluate(f"document.getElementById('{identifier}').click()")

        def rect(selector):
            return json.loads(
                evaluate(
                    "JSON.stringify(document.querySelector("
                    + json.dumps(selector)
                    + ").getBoundingClientRect().toJSON())"
                )
            )

        def wheel(selector, delta=120, ctrl=True):
            bounds = rect(selector)
            point = QPoint(
                round(bounds["x"] + bounds["width"] / 2), round(bounds["y"] + bounds["height"] / 2)
            )
            target = window.view.focusProxy() or window.view
            local = target.mapFrom(window.view, point)
            event = QWheelEvent(
                QPointF(local),
                QPointF(target.mapToGlobal(local)),
                QPoint(),
                QPoint(0, delta),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            QApplication.sendEvent(target, event)

        def key(key, shift=False):
            modifiers = Qt.KeyboardModifier.ControlModifier
            if shift:
                modifiers |= Qt.KeyboardModifier.ShiftModifier
            QTest.keyClick(window.view.focusProxy() or window.view, key, modifiers)

        def open_file(file):
            window.bridge.load_paths([file])
            wait("readerApp.activeId===" + json.dumps(str(file)), "open " + file.suffix)

        try:
            wait(
                "document.querySelectorAll('#document h2').length===100 && document.querySelector('.diagram-frame')?.dataset.status==='ready' && document.fonts.status==='loaded'",
                "document, image, table and diagram load",
            )
            header = rect(".topbar")
            sidebar = rect(".sidebar")
            original = rect("#document h2")
            wheel("#reading-scroll")
            wait(
                "document.getElementById('preview-zoom-value').textContent==='110%'",
                "native Ctrl+wheel zooms preview",
            )
            assert window.view.zoomFactor() == 1
            assert rect(".topbar") == header and rect(".sidebar") == sidebar
            assert abs(rect("#document h2")["height"] / original["height"] - 1.1) < 0.02
            print("PASS: app chrome stays fixed while rendered content scales", flush=True)
            wheel(".sidebar")
            QTest.qWait(200)
            assert (
                evaluate("readerApp.settings.previewZoom") == 110 and window.view.zoomFactor() == 1
            )
            click("preview-zoom-reset")
            assert evaluate(
                "readerApp.settings.previewZoom===100 && document.getElementById('preview-zoom-reset').textContent.trim()==='Reset'"
            )
            click("edit-mode")
            QTest.qWait(200)
            editor = rect(".source-editor:not([hidden])")
            font = evaluate(
                "getComputedStyle(document.querySelector('.source-editor:not([hidden])')).font"
            )
            key(Qt.Key.Key_Equal)
            wait("readerApp.settings.previewZoom===110", "Ctrl+plus zooms preview in edit mode")
            assert rect(".source-editor:not([hidden])") == editor
            assert (
                evaluate(
                    "getComputedStyle(document.querySelector('.source-editor:not([hidden])')).font"
                )
                == font
            )
            wheel(".source-editor:not([hidden])")
            QTest.qWait(200)
            assert (
                evaluate("readerApp.settings.previewZoom") == 110 and window.view.zoomFactor() == 1
            )
            key(Qt.Key.Key_Minus)
            wait("readerApp.settings.previewZoom===100", "Ctrl+minus zooms out")
            key(Qt.Key.Key_Equal, shift=True)
            key(Qt.Key.Key_0)
            wait("readerApp.settings.previewZoom===100", "Ctrl+0 restores 100%")
            assert path.read_text() == source

            # Pointer anchoring and both scroll directions after magnification.
            evaluate(
                "document.querySelector('#document [data-source-line=\"160\"]').scrollIntoView({block:'start',behavior:'instant'})"
            )
            QTest.qWait(200)
            anchor = rect('#document [data-source-line="160"]')
            viewport = rect("#reading-scroll")
            center = viewport["top"] + viewport["height"] / 2
            wheel("#reading-scroll")
            wait("readerApp.settings.previewZoom===110", "zoom during synchronized editing")
            QTest.qWait(150)
            assert (
                abs(
                    rect('#document [data-source-line="160"]')["top"]
                    - (center + (anchor["top"] - center) * 1.1)
                )
                < 3
            )
            print("PASS: the reading position remains under the mouse during zoom", flush=True)
            evaluate(
                "document.querySelector('#document [data-source-line=\"240\"]').scrollIntoView({block:'start',behavior:'instant'})"
            )
            wait(
                "(() => {const e=document.querySelector('.source-editor:not([hidden])');return Math.abs(e.scrollTop/parseFloat(getComputedStyle(e).lineHeight)-240)<6})()",
                "zoomed preview scroll synchronizes editor",
            )
            evaluate(
                "(() => {const e=document.querySelector('.source-editor:not([hidden])');e.scrollTop=120*parseFloat(getComputedStyle(e).lineHeight)})()"
            )
            wait(
                "(() => {const p=document.querySelector('#document [data-source-line=\"120\"]').getBoundingClientRect(),s=document.getElementById('reading-scroll').getBoundingClientRect();return Math.abs(p.top-s.top)<100})()",
                "editor scroll synchronizes zoomed preview",
            )

            click("read-mode")
            click("preview-zoom-reset")
            QTest.qWait(150)
            image_size = rect("#document img")
            table_size = rect("#document table")
            graph_size = rect(".diagram-surface")
            for _ in range(10):
                click("preview-zoom-in")
            wait("readerApp.settings.previewZoom===200", "toolbar zoom reaches 200%")
            for selector, before in [
                ("#document img", image_size),
                ("#document table", table_size),
                (".diagram-surface", graph_size),
            ]:
                assert abs(rect(selector)["height"] / before["height"] - 2) < 0.06, selector
            assert evaluate(
                "document.getElementById('reading-scroll').scrollWidth>document.getElementById('reading-scroll').clientWidth"
            )
            assert evaluate("document.documentElement.scrollWidth<=innerWidth")
            print(
                "PASS: images, tables and diagrams magnify inside the preview viewport", flush=True
            )
            for _ in range(20):
                click("preview-zoom-in")
            assert evaluate(
                "readerApp.settings.previewZoom===300 && document.getElementById('preview-zoom-in').disabled"
            )
            for _ in range(40):
                click("preview-zoom-out")
            assert evaluate(
                "readerApp.settings.previewZoom===50 && document.getElementById('preview-zoom-out').disabled"
            )
            click("preview-zoom-reset")

            pdf_path = folder / "sample.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((70, 100), "PDF zoom")
                pdf.save(pdf_path)
            open_file(pdf_path)
            wait("document.querySelector('.pdf-image')?.naturalWidth>0", "PDF image loads")
            before = rect(".pdf-page")
            overlay = rect(".pdf-block")
            for _ in range(5):
                click("preview-zoom-in")
            assert abs(rect(".pdf-page")["width"] / before["width"] - 1.5) < 0.02
            assert abs(rect(".pdf-block")["width"] / overlay["width"] - 1.5) < 0.02
            print("PASS: PDF pages and text overlays scale together", flush=True)
            click("preview-zoom-reset")
            wheel("#reading-scroll", -120, False)
            QTest.qWait(150)
            assert evaluate("readerApp.settings.previewZoom") == 100
            assert evaluate("document.getElementById('reading-scroll').scrollTop>0")
            click("preview-zoom-in")
            QTest.qWait(150)
            assert json.loads(window.bridge.settings.value("reading"))["previewZoom"] == 110
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
            window = ReaderWindow(settings_path=settings)
            window.showFullScreen()
            wait(
                "window.readerApp?.activeId && readerApp.settings.previewZoom===110 && document.getElementById('preview-zoom-value').textContent==='110%'",
                "preview zoom survives restart",
            )
            assert window.view.zoomFactor() == 1
            assert not errors, errors
            print("Preview zoom smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
