import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from reader.documents import MAX_FILE_BYTES, load_document, render_html, render_markdown


class DocumentTests(unittest.TestCase):
    def test_mermaid_source_survives_both_renderers_without_active_html(self):
        source = 'flowchart RL\n  A["سلام & English"] --> B["<script>literal</script>"]\n'
        from html import escape

        for html, _ in [
            render_markdown("```mermaid\n" + source + "```"),
            render_html(
                '<pre><code class="language-mermaid sidebar" onclick="evil()">'
                + escape(source)
                + "</code></pre>"
            ),
        ]:
            code = BeautifulSoup(html, "html.parser").select_one("pre > code.language-mermaid")
            self.assertIsNotNone(code)
            self.assertEqual(code.get_text(), source)
            self.assertNotIn("sidebar", code.get("class", []))
            self.assertNotIn("onclick", html)
            self.assertNotIn("<script>", html)

    def test_html_strips_active_content_and_page_styling(self):
        html, headings = render_html("""<!doctype html><html><head><title>Hidden title</title>
        <style>body{display:none}</style><script>alert(1)</script></head><body onload="evil()">
        <h1 id="document" class="sidebar">سلام HTML</h1><div>متن فارسی با English</div>
        <a href="#document">Jump</a><a href="javascript:alert(1)">Bad link</a>
        <iframe src="https://example.com"></iframe><form><input name="native"></form>
        <img src="https://example.com/tracker.png" onerror="evil()">
        <p style="position:fixed" onclick="evil()">Visible</p></body></html>""")
        for forbidden in [
            "<script",
            "<style",
            "<iframe",
            "<form",
            "onclick",
            "onerror",
            "onload",
            "javascript:",
            'class="sidebar"',
            "style=",
            "Hidden title",
        ]:
            self.assertNotIn(forbidden, html)
        self.assertEqual(headings[0]["id"], "doc-heading-document")
        self.assertIn('href="#doc-heading-document"', html)
        self.assertTrue(
            any(
                p.get_text() == "متن فارسی با English"
                for p in BeautifulSoup(html, "html.parser").find_all("p")
            )
        )

    def test_html_load_and_explicit_direction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.HTML"
            path.write_text(
                '<h1>Test</h1><p dir="ltr">English با فارسی</p><pre>x = 2</pre>', encoding="utf-8"
            )
            doc = load_document(path)
            self.assertEqual(doc.format, "HTML")
            self.assertIn('dir="ltr"', doc.html)
            self.assertEqual(len(doc.headings), 1)
        html, _ = render_html('<html dir="rtl"><body dir="ltr"><p>فارسی English</p></body></html>')
        self.assertTrue(html.startswith('<div dir="ltr">'))

    def test_persian_english_structures_and_unique_anchors(self):
        html, headings = render_markdown(
            "# سلام Hello\n\n# سلام Hello\n\n# سلام Hello-1\n\n| فارسی | English |\n| --- | --- |\n| الف | test |\n\n~~گذشته~~\n\n[برو](#سلام-hello)"
        )
        self.assertEqual(len({h["id"] for h in headings}), 3)
        self.assertIsNotNone(BeautifulSoup(html, "html.parser").table)
        self.assertIn("<s>گذشته</s>", html)
        self.assertIn('href="#doc-heading-', html)
        self.assertTrue(all(h["id"].startswith("doc-heading-") for h in headings))

    def test_active_html_and_javascript_are_inert(self):
        html, _ = render_markdown(
            "<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n[x](javascript:alert(3))\n\n[x](data:text/html,evil)"
        )
        self.assertNotIn("<script", html)
        self.assertNotIn("<img ", html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('href="data:', html)

    def test_code_is_escaped_and_language_classes_remain(self):
        html, _ = render_markdown(
            '```python\nprint("سلام")\n```\n\n```unknown\n<script>bad</script>\n```'
        )
        self.assertIn("language-python", html)
        self.assertIn("سلام", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_local_images_are_resolved_and_remote_images_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "image.png").write_bytes(b"example")
            html, _ = render_markdown(
                "![محلی](image.png)\n\n![بیرونی](https://example.com/pixel.png)\n\n![خارج](../outside.png)",
                base,
            )
            self.assertIn((base / "image.png").as_uri(), html)
            self.assertNotIn('src="https:', html)
            self.assertEqual(html.count("image-placeholder"), 2)

    def test_utf8_and_utf16_bom_and_empty_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "متن.MD"
            for codec in ["utf-8", "utf-8-sig", "utf-16"]:
                path.write_bytes("# سلام English".encode(codec))
                self.assertIn("سلام", load_document(path).html)
            path.write_text("")
            self.assertEqual(load_document(path).words, 0)

    def test_invalid_binary_large_and_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.md"
            for data in [b"\xffbroken", b"a\x00b", b"a" * (MAX_FILE_BYTES + 1)]:
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    load_document(path)
            with self.assertRaises(FileNotFoundError):
                load_document(Path(folder) / "missing.md")
            with self.assertRaises(ValueError):
                load_document(Path(folder) / "test.exe")


if __name__ == "__main__":
    unittest.main()
