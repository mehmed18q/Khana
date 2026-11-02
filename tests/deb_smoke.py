"""Validate the installer payload and desktop identity without installing it."""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bundle_smoke import ROOT, PackagedApp
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

sys.path.insert(0, str(ROOT))
import pymupdf
from api_fixture import api_server, api_spec

from reader.source_formatting import beautify_source
from reader.word_documents import load_word, save_word


def main():
    _app = QCoreApplication.instance() or QCoreApplication([])
    package = ROOT / "dist/khana_0.5.4-1_amd64.deb"
    fields = subprocess.check_output(["dpkg-deb", "--field", str(package)], text=True)
    assert "Package: khana\n" in fields and "Architecture: amd64\n" in fields
    with tempfile.TemporaryDirectory(prefix="khana-deb-") as temporary:
        folder = Path(temporary)
        payload = folder / "payload"
        subprocess.run(["dpkg-deb", "--extract", str(package), str(payload)], check=True)
        subprocess.run(["dpkg-deb", "--control", str(package), str(folder / "control")], check=True)
        subprocess.run(
            ["md5sum", "--check", "--quiet", str(folder / "control/md5sums")],
            cwd=payload,
            check=True,
        )
        assert sorted(p.name for p in (folder / "control").iterdir()) == ["control", "md5sums"]
        entry = payload / "usr/share/applications/io.khana.Khana.desktop"
        subprocess.run(["desktop-file-validate", str(entry)], check=True)
        assert (payload / "usr/bin/khana").readlink() == Path("/opt/khana/Khana")
        executable = payload / "opt/khana/Khana"
        assert (
            subprocess.check_output([str(executable), "--version"], text=True).strip()
            == "Khana 0.5.4"
        )
        for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
            icon = QImage(
                str(payload / f"usr/share/icons/hicolor/{size}x{size}/apps/io.khana.Khana.png")
            )
            assert icon.width() == size and icon.height() == size
            assert icon.hasAlphaChannel()
        print(
            "PASS: installer metadata, payload hashes, command, version and all logo sizes",
            flush=True,
        )

        # Only the fixture's Exec/TryExec paths are relocated. The real package
        # always registers /usr/bin/khana. No host menu/config is modified.
        data = folder / "xdg-data"
        shutil.copytree(payload / "usr/share/icons", data / "icons")
        applications = data / "applications"
        applications.mkdir(parents=True)
        (applications / entry.name).write_text(
            entry.read_text().replace("/usr/bin/khana", str(executable))
        )
        subprocess.run(["update-desktop-database", str(applications)], check=True)
        env = {
            **os.environ,
            "XDG_DATA_HOME": str(data),
            "XDG_CONFIG_HOME": str(folder / "registry-config"),
        }
        result = subprocess.check_output(
            ["/usr/bin/python3", str(ROOT / "tests/desktop_registration.py"), str(data)],
            env=env,
            text=True,
        )
        print(
            "PASS: GNOME search finds Khana, resolves the installed logo and matches the desktop class:",
            result.strip(),
            flush=True,
        )

        running = None
        try:
            running = PackagedApp(executable, folder, extra_env={"WAYLAND_DEBUG": "client"})
            assert running.evaluate(
                "document.querySelector('.version-note').textContent.includes('0.5.4')"
            )
            dimensions = "[document.querySelector('.topbar').getBoundingClientRect().width, document.querySelector('.sidebar').getBoundingClientRect().width]"
            before = running.evaluate(dimensions)
            x, y = running.evaluate(
                "(()=>{const r=document.getElementById('reading-scroll').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()"
            )
            running.call(
                "Input.dispatchMouseEvent",
                {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": -120, "modifiers": 2},
            )
            running.wait(
                "document.getElementById('preview-zoom-value').textContent==='110%'",
                "packaged Ctrl+wheel zooms only the preview",
            )
            assert running.evaluate(dimensions) == before
            running.evaluate("document.getElementById('preview-zoom-reset').click()")
            assert running.evaluate("readerApp.settings.previewZoom===100")
            running.evaluate("document.getElementById('minimize-button').click()")
            running.close()
            if os.environ.get("XDG_SESSION_TYPE") == "wayland":
                assert 'set_app_id("io.khana.Khana")' in (folder / "app.log").read_text()
                assert "set_minimized()" in (folder / "app.log").read_text()
                print(
                    "PASS: actual Wayland app ID matches the installable desktop entry", flush=True
                )
            # Exercise SQLite and the annotation UI in the frozen executable,
            # including a full process restart with the same user configuration.
            source = folder / "reading.md"
            original = "# Reading\n\nA place to remember.\n\nیادداشت روی متن فارسی و English.\n"
            source.write_text(original)
            running = PackagedApp(executable, folder, [source])
            running.evaluate("document.getElementById('star-document').click()")
            running.wait(
                "document.getElementById('star-document').getAttribute('aria-pressed')==='true'",
                "packaged library saves favorites",
            )
            running.evaluate(
                "document.querySelector('[data-reading-block=\"1\"] .annotation-tools button').click(); document.getElementById('annotation-name').value='Checkpoint'; document.getElementById('annotation-save').click()"
            )
            running.wait(
                "!document.getElementById('annotation-dialog').open && document.getElementById('annotation-count').textContent==='1'",
                "packaged app saves a reading mark",
            )
            running.evaluate(
                "document.querySelector('[data-reading-block=\"2\"] .annotation-tools button:last-child').click(); document.getElementById('annotation-name').value='Thoughts'"
            )
            running.evaluate(
                'document.getElementById("annotation-body").value='
                + json.dumps("یادداشت من\nEnglish note")
            )
            running.evaluate("document.getElementById('annotation-save').click()")
            running.wait(
                "!document.getElementById('annotation-dialog').open && document.getElementById('annotation-count').textContent==='2'",
                "packaged app saves a mixed-language note",
            )
            running.close()
            running = PackagedApp(executable, folder)
            running.wait(
                "document.getElementById('annotation-count').textContent==='2' && document.querySelectorAll('.annotation-badge').length===2",
                "documents, marks and notes survive an executable restart",
            )
            assert running.evaluate(
                "document.getElementById('star-document').getAttribute('aria-pressed')==='true'"
            )
            running.evaluate(
                "document.getElementById('annotations-button').click(); document.querySelectorAll('.annotation-actions button:last-child')[1].click()"
            )
            running.wait(
                "document.getElementById('annotation-count').textContent==='1'",
                "packaged app deletes a note",
            )
            running.evaluate(
                "document.querySelector('.annotation-actions button:last-child').click()"
            )
            running.wait(
                "document.getElementById('annotation-count').textContent==='0'",
                "packaged app deletes a mark",
            )
            running.close()
            running = PackagedApp(executable, folder)
            assert running.evaluate(
                "document.getElementById('annotation-count').textContent==='0' && !document.querySelector('.annotation-badge')"
            )
            assert source.read_text() == original
            running.close()
            print(
                "PASS: annotation deletions persist and the source file stays unchanged", flush=True
            )
            data_file = folder / "sample.json"
            data_file.write_text('{"hello": "سلام"}')
            running = PackagedApp(executable, folder, [data_file])
            running.wait(
                "document.getElementById('document-format').textContent==='JSON'",
                "packaged JSON reader",
            )
            running.evaluate("readerApp.setEditMode(true)")
            assert running.evaluate(
                "document.getElementById('format-toolbar').hidden && document.getElementById('sync-scroll').checked"
            )
            formatted = beautify_source(data_file.read_text(), "JSON")
            running.evaluate("document.getElementById('beautify-button').click()")
            running.wait(
                "document.querySelector('.source-editor:not([hidden])').value==="
                + json.dumps(formatted),
                "packaged JSON beautifier",
            )
            running.evaluate("readerApp.command('save')")
            running.wait(
                "document.getElementById('save-status').textContent==='Saved'",
                "packaged formatted JSON saves",
            )
            assert data_file.read_text() == formatted
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            (artifacts / "packaged-json.png").write_bytes(
                base64.b64decode(running.call("Page.captureScreenshot", {"format": "png"})["data"])
            )
            running.close()
            for suffix, source in [
                ("yaml", '# Keep comment\napp:\n     name: "سلام"\n     values: [1,2]\n'),
                ("xml", "<root><name>سلام</name><value>2</value></root>"),
            ]:
                file = folder / ("format." + suffix)
                file.write_text(source)
                running = PackagedApp(executable, folder, [file])
                running.wait(
                    "document.getElementById('current-filename').textContent==="
                    + json.dumps(file.name),
                    "packaged open " + suffix,
                )
                running.evaluate(
                    "readerApp.setEditMode(true);document.getElementById('beautify-button').click()"
                )
                formatted = beautify_source(source, suffix.upper())
                running.wait(
                    "document.querySelector('.source-editor:not([hidden])').value==="
                    + json.dumps(formatted),
                    "packaged beautifier " + suffix,
                )
                running.evaluate("readerApp.command('save')")
                running.wait(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "packaged formatted source saves",
                )
                assert file.read_text() == formatted
                running.close()
            for suffix, spec in [
                (
                    "yaml",
                    'openapi: 3.0.3\ninfo: {title: Packaged API, version: "1"}\npaths:\n  /hello:\n    get:\n      responses:\n        200: {description: OK}\n',
                ),
                (
                    "json",
                    '{"swagger":"2.0","info":{"title":"Packaged API","version":"1"},"paths":{"/hello":{"get":{"responses":{"200":{"description":"OK"}}}}}}',
                ),
            ]:
                file = folder / ("api." + suffix)
                file.write_text(spec)
                running = PackagedApp(executable, folder, [file])
                shadow = "document.querySelector('.swagger-host')?.shadowRoot"
                running.wait(
                    shadow + "?.querySelectorAll('[data-api-operation]').length===1",
                    "packaged Swagger UI " + suffix,
                )
                running.evaluate(shadow + ".querySelector('.opblock-summary-control').click()")
                running.wait(
                    shadow + "?.querySelectorAll('.responses-table').length===1",
                    "packaged Swagger response",
                )
                running.evaluate(
                    "readerApp.setEditMode(true);const e=document.querySelector('.source-editor:not([hidden])');e.value=e.value.replace('Packaged API','Updated API');e.dispatchEvent(new Event('input',{bubbles:true}));readerApp.command('save')"
                )
                running.wait(
                    shadow + "?.querySelector('.info .title')?.textContent.includes('Updated API')",
                    "packaged API live preview",
                )
                running.wait(
                    "document.getElementById('save-status').textContent==='Saved'",
                    "packaged API save",
                )
                assert "Updated API" in file.read_text()
                running.evaluate("document.getElementById('api-preview-source').click()")
                running.wait(
                    "!!document.querySelector('.structured-source')", "packaged API source view"
                )
                running.close()
            with api_server() as (url, received):
                file = folder / "requests.json"
                file.write_text(json.dumps(api_spec(url)))
                shadow = "document.querySelector('.swagger-host')?.shadowRoot"
                running = PackagedApp(executable, folder, [file])
                running.wait(
                    shadow + "?.querySelectorAll('[data-api-operation]').length===10",
                    "packaged request controls",
                )
                assert not received

                def execute(path):
                    block = (
                        shadow
                        + ".querySelector("
                        + json.dumps(f'[data-api-operation="GET {path}"]')
                        + ")"
                    )
                    running.evaluate(block + ".querySelector('.opblock-summary-control').click()")
                    running.wait(
                        block + ".querySelector('.try-out__btn')!==null", "packaged Try it out"
                    )
                    running.evaluate(block + ".querySelector('.try-out__btn').click()")
                    running.evaluate(block + ".querySelector('.execute').click()")
                    running.wait(
                        block
                        + ".querySelector('.live-responses-table tbody .response-col_status')?.textContent.includes('200')",
                        "packaged HTTP response",
                    )

                execute("/public")
                assert (
                    received[-1]["path"] == "/public"
                    and "authorization" not in received[-1]["headers"]
                )
                running.evaluate(shadow + ".querySelector('.auth-wrapper .authorize').click()")
                container = (
                    "[..."
                    + shadow
                    + ".querySelectorAll('.auth-container')].find(n=>n.querySelector('h4')?.textContent.startsWith('token'))"
                )
                running.wait("!!(" + container + ")", "packaged Authorize dialog")
                running.evaluate(
                    "(()=>{const input=("
                    + container
                    + ').querySelector("input");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,"packaged-example-token");input.dispatchEvent(new Event("input",{bubbles:true}));})()'
                )
                running.evaluate("(" + container + ").querySelector('.authorize').click()")
                running.wait(
                    "(" + container + ").textContent.includes('Authorized')",
                    "packaged token accepted",
                )
                running.evaluate(shadow + ".querySelector('.btn-done').click()")
                execute("/bearer")
                assert received[-1]["headers"]["authorization"] == "Bearer packaged-example-token"
                (artifacts / "packaged-api-request.png").write_bytes(
                    base64.b64decode(
                        running.call("Page.captureScreenshot", {"format": "png"})["data"]
                    )
                )
                running.close()
                running = PackagedApp(executable, folder, [file])
                running.wait(
                    shadow + "?.querySelectorAll('[data-api-operation]').length===10",
                    "packaged API restart",
                )
                execute("/bearer")
                assert "authorization" not in received[-1]["headers"]
                assert "packaged-example-token" not in file.read_text()
                running.close()
                print(
                    "PASS: packaged public/authenticated requests and credentials cleared on restart",
                    flush=True,
                )
            word_file = folder / "word.docx"
            word_file.write_bytes(save_word("<h1>Packaged Word</h1>", ".docx"))
            running = PackagedApp(executable, folder, [word_file])
            running.wait(
                "document.getElementById('document-format').textContent==='Word'",
                "packaged Word conversion",
            )
            running.evaluate(
                "readerApp.setEditMode(true); const e=document.querySelector('.source-editor:not([hidden])'); e.value='<h1>Saved Word</h1>'; e.dispatchEvent(new Event('input',{bubbles:true})); readerApp.command('save')"
            )
            running.wait(
                "document.getElementById('save-status').textContent==='Saved'",
                "packaged Word export",
            )
            assert "Saved Word" in load_word(word_file.read_bytes(), ".docx")
            running.close()
            pdf_file = folder / "sample.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((70, 80), "Packaged PDF text", fontsize=16)
                pdf.save(pdf_file)
            running = PackagedApp(executable, folder, [pdf_file])
            running.wait(
                "document.querySelector('.pdf-image')?.naturalWidth>0",
                "packaged PDF rendering with bundled native libraries",
            )
            (artifacts / "packaged-pdf.png").write_bytes(
                base64.b64decode(running.call("Page.captureScreenshot", {"format": "png"})["data"])
            )
            running.evaluate(
                "document.querySelector('.pdf-edit').click(); document.getElementById('pdf-text-input').value='Saved PDF text'; document.getElementById('pdf-apply').click()"
            )
            running.wait(
                "!document.getElementById('pdf-dialog').open && document.querySelector('.pdf-text').textContent==='Saved PDF text'",
                "packaged PDF text replacement",
            )
            running.evaluate("readerApp.command('save')")
            running.wait(
                "document.getElementById('save-status').textContent==='Saved'", "packaged PDF save"
            )
            running.close()
            with pymupdf.open(pdf_file) as pdf:
                assert "Saved PDF text" in pdf[0].get_text()
            if os.environ.get("DISPLAY"):
                running = PackagedApp(executable, folder, platform="xcb")
                listing = subprocess.check_output(["xprop", "-root", "_NET_CLIENT_LIST"], text=True)
                matched = False
                for window in re.findall(r"0x[0-9a-fA-F]+", listing):
                    properties = subprocess.check_output(
                        ["xprop", "-id", window, "_NET_WM_PID", "WM_CLASS", "_NET_WM_ICON"],
                        text=True,
                    )
                    if re.search(
                        r"_NET_WM_PID\(CARDINAL\) = " + str(running.process.pid) + r"\b", properties
                    ):
                        assert '"Khana"' in properties
                        assert "_NET_WM_ICON(CARDINAL)" in properties
                        matched = True
                assert matched, "X11 application window was not found"
                running.close()
                print("PASS: actual X11 class and window icon match the installed app", flush=True)
            print(f"Debian package smoke test passed: {package}", flush=True)
        finally:
            if running:
                running.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
