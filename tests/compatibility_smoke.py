"""Run the packaged UI on Ubuntu 24.04/Xvfb or a newer desktop host."""

import json
import sys
import tempfile
from pathlib import Path

from bundle_smoke import PackagedApp
from PySide6.QtCore import QCoreApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from reader import VERSION


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="khana-compatibility-") as folder:
        folder = Path(folder)
        source = folder / "reading.md"
        source.write_text(
            "# Compatibility\n\nhello helllo سلام سللام\n\n123 / ۱۲۳ / ١٢٣\n\n"
            "| Title | Value |\n| --- | --- |\n| first | second |\n",
            encoding="utf-8",
        )
        running = PackagedApp(executable, folder, [source])
        try:
            assert running.evaluate(
                f"document.getElementById('app-version').textContent === {json.dumps('/ ' + VERSION)}"
            )
            running.evaluate(
                "readerApp.command('search');document.getElementById('search-input').value='۱۲۳';readerApp.search()"
            )
            assert running.evaluate(
                "document.getElementById('search-count').textContent==='1 of 3'"
            )
            running.evaluate(
                "document.getElementById('search-close').click();readerApp.setEditMode(true)"
            )
            running.wait(
                "(()=>{const words=[...(CSS.highlights.get('reader-spelling')||[])].map(range=>range.toString());return words.includes('helllo')&&words.includes('سللام')})()",
                "packaged Persian/English spelling and equivalent digit search",
            )
            running.evaluate(
                "document.getElementById('ui-language-button').click();document.querySelector('#ui-language-menu [data-value=fa]').click()"
            )
            running.wait(
                "document.documentElement.dir==='rtl'&&document.getElementById('save-button').textContent.includes('ذخیره')",
                "packaged Persian interface",
            )
            running.evaluate("document.querySelector('.structure-edit').click()")
            running.wait("document.getElementById('table-dialog').open", "existing table opens")
            running.evaluate(
                "const cell=document.querySelector('#table-grid input[data-row=\"1\"][data-col=\"0\"]');cell.value='edited';cell.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('table-insert').click();readerApp.command('save')"
            )
            running.wait(
                "!document.getElementById('save-button').classList.contains('dirty')&&document.querySelector('#document td')?.textContent==='edited'",
                "table edit preview",
            )
            running.evaluate(
                "document.getElementById('ui-language-button').click();document.querySelector('#ui-language-menu [data-value=en]').click()"
            )
            running.wait(
                "document.getElementById('save-status').textContent==='Saved'", "packaged save"
            )
            assert "| edited | second |" in source.read_text()
            running.close()
        finally:
            running.stop()
    return 0 if app else 1


if __name__ == "__main__":
    raise SystemExit(main())
