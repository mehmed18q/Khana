"""Measure real WebEngine navigation on a large mixed-language document."""

import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from reader.ui.window import ReaderWindow


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="khana-performance-") as folder:
        path = Path(folder) / "large.md"
        path.write_text(
            Path(sys.argv[1]).read_text()
            if len(sys.argv) > 1
            else "\n\n".join(
                f"Paragraph {i} متن فارسی ۱۲۳۴ and English words." for i in range(3000)
            )
        )
        window = ReaderWindow([path], settings_path=Path(folder) / "settings.ini")
        window.show()

        def js(script):
            values = []
            window.page.runJavaScript(script, values.append)
            deadline = time.monotonic() + 60
            while not values and time.monotonic() < deadline:
                QTest.qWait(10)
            assert values, "JavaScript timeout"
            return values[0]

        def measure(script):
            value = js(
                "(()=>{const start=performance.now();"
                + script
                + ";return performance.now()-start})()"
            )
            print(f"{script[:60]}: {value:.1f} ms", flush=True)
            return value

        try:
            deadline = time.monotonic() + 60
            while not js("!!window.readerApp?.activeId && document.fonts.status==='loaded'"):
                assert time.monotonic() < deadline
                QTest.qWait(50)
            QTest.qWait(500)
            result = {}
            queries = []
            window.bridge.library.connection.set_trace_callback(queries.append)
            result["open_search_ms"] = measure("readerApp.command('search')")
            js(
                "document.getElementById('search-input').value="
                + json.dumps("سؤال" if len(sys.argv) > 1 else "Paragraph")
            )
            result["first_search_ms"] = measure("readerApp.search()")
            result["next_5_ms"] = measure(
                "for(let i=0;i<5;i++)document.getElementById('search-next').click()"
            )
            js("document.getElementById('search-close').click()")
            result["open_line_ms"] = measure("readerApp.command('go-to-line')")
            js("document.getElementById('go-to-line-input').value='2500'")
            result["jump_reading_ms"] = measure(
                "document.getElementById('go-to-line-form').requestSubmit()"
            )
            result["edit_mode_ms"] = measure("readerApp.setEditMode(true)")
            QTest.qWait(300)
            result["jump_editor_ms"] = measure(
                "readerApp.command('go-to-line');document.getElementById('go-to-line-input').value='2000';document.getElementById('go-to-line-form').requestSubmit()"
            )
            QTest.qWait(300)
            result["typing_ms"] = measure(
                "document.querySelector('.source-editor:not([hidden])').focus();document.execCommand('insertText',false,'test')"
            )
            result["sql_statements"] = len(queries)
            print(json.dumps(result, indent=2), flush=True)
            assert not queries, "Navigation and typing must not query SQLite"
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0 if app else 1


if __name__ == "__main__":
    raise SystemExit(main())
