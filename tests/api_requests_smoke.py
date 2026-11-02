"""Use real Swagger controls against a local HTTP server, without CORS exemptions."""

import base64
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api_fixture import api_server, api_spec
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
    with (
        tempfile.TemporaryDirectory(prefix="khana-requests-") as tmp,
        api_server() as (url, received),
    ):
        folder = Path(tmp)
        path = folder / "requests.json"
        original = json.dumps(api_spec(url), indent=2, ensure_ascii=False)
        path.write_text(original)
        window = ReaderWindow([path], settings_path=folder / "settings.ini")
        window.showFullScreen()
        root = "document.querySelector('.swagger-host')?.shadowRoot"

        def evaluate(script):
            values = []
            window.page.runJavaScript(script, lambda result: values.append(result))
            deadline = time.monotonic() + 10
            while not values and time.monotonic() < deadline:
                QTest.qWait(20)
            assert values, script[:100]
            return values[0]

        def wait(script, label):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if evaluate(script):
                    print("PASS:", label, flush=True)
                    return
                QTest.qWait(50)
            raise AssertionError(
                f"{label}: {errors}; " + str(evaluate(root + "?.textContent.slice(-2500)"))
            )

        def click(identifier):
            evaluate(f"document.getElementById('{identifier}').click()")

        def block(path, method="GET"):
            return (
                root
                + ".querySelector("
                + json.dumps(f'[data-api-operation="{method} {path}"]')
                + ")"
            )

        def execute(path, method="GET", status=200):
            target = block(path, method)
            evaluate(
                "if (!"
                + target
                + ".classList.contains('is-open')) "
                + target
                + ".querySelector('.opblock-summary-control').click()"
            )
            wait(target + ".querySelector('.try-out__btn')!==null", "Try it out " + path)
            evaluate(
                "if (!"
                + target
                + ".querySelector('.execute')) "
                + target
                + ".querySelector('.try-out__btn').click()"
            )
            wait(target + ".querySelector('.execute')!==null", "Execute available " + path)
            count = len(received)
            evaluate(target + ".querySelector('.execute').click()")
            if status is not None:
                deadline = time.monotonic() + 10
                while len(received) == count and time.monotonic() < deadline:
                    QTest.qWait(20)
                assert len(received) > count, "Execute must send a new request"
                wait(
                    target
                    + ".querySelector('.live-responses-table tbody .response-col_status')?.textContent.includes("
                    + json.dumps(str(status))
                    + ")",
                    "HTTP response " + path,
                )
            return target

        def authorize(name, values):
            evaluate(root + ".querySelector('.auth-wrapper .authorize').click()")
            wait(root + ".querySelector('.dialog-ux')!==null", "Authorize dialog")
            container = (
                "[..."
                + root
                + ".querySelectorAll('.auth-container')].find(n=>n.querySelector('h4')?.textContent.trim().startsWith("
                + json.dumps(name)
                + "))"
            )
            assert evaluate("!!(" + container + ")"), evaluate(
                root + ".querySelector('.dialog-ux').textContent"
            )
            for index, value in enumerate(values):
                evaluate(
                    "(()=>{const input=("
                    + container
                    + ').querySelectorAll("input")['
                    + str(index)
                    + '];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,'
                    + json.dumps(value)
                    + ');input.dispatchEvent(new Event("input",{bubbles:true}));})()'
                )
            evaluate("(" + container + ").querySelector('.authorize').click()")
            wait("(" + container + ").textContent.includes('Authorized')", "authorize " + name)
            evaluate(root + ".querySelector('.btn-done').click()")

        try:
            wait(
                root + "?.querySelectorAll('[data-api-operation]').length===10",
                "request-capable Swagger loads",
            )
            QTest.qWait(300)
            assert not received, "Opening a spec must never send a request"
            execute("/public")
            assert (
                received[-1]["path"] == "/public" and "authorization" not in received[-1]["headers"]
            )
            (ROOT / "artifacts").mkdir(exist_ok=True)
            window.grab().save(str(ROOT / "artifacts/api-request-preview.png"))
            authorize("token", ["example-bearer"])
            window.grab().save(str(ROOT / "artifacts/api-authorization.png"))
            execute("/bearer")
            assert received[-1]["headers"]["authorization"] == "Bearer example-bearer"
            authorize("basic", ["example-user", "example-password"])
            execute("/basic")
            assert (
                received[-1]["headers"]["authorization"]
                == "Basic " + base64.b64encode(b"example-user:example-password").decode()
            )
            authorize("key", ["example-api-key"])
            execute("/api-key")
            assert received[-1]["headers"]["x-api-key"] == "example-api-key"
            authorize("queryKey", ["example-query-key"])
            execute("/query-key")
            assert received[-1]["path"] == "/query-key?api_key=example-query-key"
            authorize("oauth", ["example-oauth-token"])
            execute("/oauth")
            assert received[-1]["headers"]["authorization"] == "Bearer example-oauth-token"
            assert not any("never-fetch-token" in request["path"] for request in received)
            execute("/echo/{id}", "POST")
            assert received[-1]["path"] == "/echo/42?q=hello"
            assert json.loads(received[-1]["body"]) == {"name": "سلام"}
            execute("/unauthorized", status=401)
            execute("/redirect", status=302)
            assert not any(request["path"] == "/redirect-target" for request in received), (
                "Redirect must not forward credentials"
            )
            target = execute("/slow", status=None)
            wait(
                root
                + ".querySelector('.api-request-settings button[type=button]').disabled===false",
                "request cancellation becomes available",
            )
            evaluate(root + ".querySelector('.api-request-settings button[type=button]').click()")
            wait(target + ".textContent.includes('Request cancelled')", "cancel a pending request")
            # The same document keeps credentials through a preview remount.
            click("api-preview-source")
            click("api-preview-swagger")
            wait(
                root + "?.querySelectorAll('[data-api-operation]').length===10",
                "return from source view",
            )
            execute("/bearer")
            assert received[-1]["headers"]["authorization"] == "Bearer example-bearer"
            execute("/public")
            assert "authorization" not in received[-1]["headers"], (
                "public operation must stay unauthenticated"
            )
            second = folder / "second.json"
            second.write_text(original)
            window.bridge.load_paths([second])
            wait(
                "readerApp.activeId==="
                + json.dumps(str(second))
                + " && "
                + root
                + "?.querySelectorAll('[data-api-operation]').length===10",
                "a separate API document loads",
            )
            execute("/bearer")
            assert "authorization" not in received[-1]["headers"], (
                "credentials must not cross documents"
            )
            # An edited definition must cancel old requests even if its tab is hidden.
            evaluate("readerApp.showDocument(" + json.dumps(str(path)) + ")")
            completed = []
            window.bridge.apiResponse.connect(completed.append)
            execute("/slow", status=None)
            wait(
                root
                + ".querySelector('.api-request-settings button[type=button]').disabled===false",
                "background request starts",
            )
            click("edit-mode")
            evaluate(
                "(()=>{const field=document.querySelector('.source-editor:not([hidden])');field.value="
                + json.dumps(original.replace("Local Request Test", "Updated Request Test"))
                + ";field.dispatchEvent(new Event('input',{bubbles:true}));readerApp.showDocument("
                + json.dumps(str(second))
                + ");})()"
            )
            deadline = time.monotonic() + 5
            while not completed and time.monotonic() < deadline:
                QTest.qWait(20)
            assert completed and "cancelled" in json.loads(completed[-1]).get("error", ""), (
                completed
            )
            evaluate("readerApp.showDocument(" + json.dumps(str(path)) + ")")
            wait(
                root
                + "?.querySelector('.info .title')?.textContent.includes('Updated Request Test')",
                "background definition change rebuilds API view",
            )
            execute("/bearer")
            assert received[-1]["headers"]["authorization"] == "Bearer example-bearer"
            evaluate("readerApp.showDocument(" + json.dumps(str(second)) + ")")
            # An explicit base URL override takes effect without editing the spec.
            evaluate(
                "(()=>{const input="
                + root
                + ".querySelector('#api-base-url');input.value="
                + json.dumps(url + "/v2")
                + ";})()"
            )
            evaluate(root + ".querySelector('.api-server-form').requestSubmit()")
            target = block("/public")
            execute("/public")
            assert received[-1]["path"] == "/v2/public", (
                received[-1]["path"],
                evaluate(root + ".querySelector('.api-request-status').textContent"),
            )
            assert path.read_text() == original and second.read_text() == original
            evaluate("readerApp.showDocument(" + json.dumps(str(path)) + ")")
            wait(
                root + "?.querySelectorAll('[data-api-operation]').length===10",
                "return to authorized document",
            )
            click("edit-mode")
            evaluate(
                "(()=>{const field=document.querySelector('.source-editor:not([hidden])');field.value="
                + json.dumps(original.replace(url, url + "/changed"))
                + ";field.dispatchEvent(new Event('input',{bubbles:true}));})()"
            )
            wait(
                root + "?.querySelector('.servers')?.textContent.includes('/changed')",
                "edited API server is previewed",
            )
            execute("/bearer")
            assert (
                received[-1]["path"] == "/changed/bearer"
                and "authorization" not in received[-1]["headers"]
            )
            print("PASS: changing servers in the source clears authorization", flush=True)
            legacy = folder / "legacy.json"
            legacy.write_text(
                json.dumps(
                    {
                        "swagger": "2.0",
                        "info": {"title": "Legacy request", "version": "1"},
                        "schemes": ["http"],
                        "host": url.removeprefix("http://"),
                        "basePath": "/v2",
                        "paths": {
                            "/public": {"get": {"responses": {"200": {"description": "OK"}}}}
                        },
                    }
                )
            )
            window.bridge.load_paths([legacy])
            wait(
                root + "?.querySelectorAll('[data-api-operation]').length===1",
                "Swagger 2 request loads",
            )
            execute("/public")
            assert received[-1]["path"] == "/v2/public"
            # Neither QSettings nor the library may persist auth secrets.
            window.bridge.settings.sync()
            for file in folder.iterdir():
                if file.is_file() and file.suffix != ".json":
                    assert (
                        b"example-bearer" not in file.read_bytes()
                        and b"example-password" not in file.read_bytes()
                    )
            assert not errors, errors
            print("API request smoke test passed.", flush=True)
        finally:
            window.allow_close = True
            window.close()
            window.page.deleteLater()
            QTest.qWait(100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
