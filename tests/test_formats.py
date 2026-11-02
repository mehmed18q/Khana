import json
import tempfile
import unittest
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup

from reader.documents import load_document, render_source
from reader.editing import EditSession


class FormatTests(unittest.TestCase):
    def test_literal_formats_and_save_as_preserve_content(self):
        cases = {
            "json": ("JSON", '{\n  "متن": "English <script>"\n}'),
            "yaml": ("YAML", "name: سلام\nmessage: |\n  multiline\n  text\n"),
            "yml": ("YAML", "enabled: true\n"),
            "log": ("LOG", "[INFO] <b>literal</b>\nسلام\n"),
            "conf": ("CONF", "# comment\n[main]\nname = test\n"),
            "ini": ("CONF", "key=value"),
            "xml": ("XML", "<root>\n <title>سلام</title>\n</root>"),
        }
        with tempfile.TemporaryDirectory() as directory:
            for ext, (fmt, source) in cases.items():
                with self.subTest(ext=ext):
                    path = Path(directory) / ("source." + ext.upper())
                    path.write_text(source)
                    doc = load_document(path)
                    self.assertEqual(doc.format, fmt)
                    soup = BeautifulSoup(doc.html, "html.parser")
                    self.assertEqual(soup.code.get_text(), source)
                    self.assertIsNone(soup.script)
                    self.assertIsNone(soup.find("root"))
                    session = EditSession.opened(doc)
                    doc.source += "\nEdited"
                    target = path.with_name("copy." + ext)
                    session.save(target, None)
                    self.assertEqual(target.read_text(), source + "\nEdited")
                    self.assertEqual(path.read_text(), source)

    def test_source_maps_cover_markdown_html_and_code(self):
        source = "# Title\n\nFirst\nline\n\n```python\na=1\n```\n"
        soup = BeautifulSoup(render_source(source, "Markdown")["html"], "html.parser")
        self.assertEqual(soup.h1["data-source-line"], "0")
        self.assertEqual(soup.p["data-source-line"], "2")
        self.assertEqual(soup.pre["data-source-line"], "5")
        self.assertEqual(soup.pre["data-source-end"], "8")
        soup = BeautifulSoup(
            render_source('<h1 data-source-line="999">Title</h1>\n<p>Text</p>', "HTML")["html"],
            "html.parser",
        )
        self.assertEqual(soup.h1["data-source-line"], "0")
        self.assertEqual(soup.p["data-source-line"], "1")

    def test_absolute_image_paths_outside_document_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            image = folder / "عکس with spaces.png"
            image.write_bytes(b"fixture")
            document = folder / "documents"
            document.mkdir()
            for fmt, source in [
                ("Markdown", f"![Photo](<{image.as_uri()}>)"),
                ("HTML", f'<img src="{image.as_uri()}" alt="Photo">'),
            ]:
                soup = BeautifulSoup(render_source(source, fmt, document)["html"], "html.parser")
                self.assertEqual(soup.img["src"], image.as_uri())

    def test_pdf_text_edit_retains_pages_graphics_and_unedited_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((60, 80), "Original text", fontsize=18)
                page.insert_text((60, 180), "Keep this text", fontsize=14)
                page.draw_rect((50, 200, 150, 270), color=(1, 0, 0))
                pdf.new_page()
                pdf.save(path)
            doc = load_document(path)
            session = EditSession.opened(doc)
            state = json.loads(doc.source)
            state["edits"]["0:0"] = "Updated text"
            doc.source = json.dumps(state)
            target = Path(directory) / "changed.pdf"
            session.save(target, None)
            with pymupdf.open(target) as pdf:
                self.assertEqual(len(pdf), 2)
                self.assertIn("Updated text", pdf[0].get_text())
                self.assertIn("Keep this text", pdf[0].get_text())
                self.assertNotIn("Original text", pdf[0].get_text())
                self.assertEqual(len(pdf[0].get_drawings()), 1)
            with pymupdf.open(path) as pdf:
                self.assertIn("Original text", pdf[0].get_text())

    def test_image_only_pdf_is_read_only(self):
        from reader.pdf_documents import load_pdf, render_pdf

        with pymupdf.open() as pdf:
            pdf.new_page().draw_rect((10, 10, 100, 100), fill=(0.3, 0.3, 0.3))
            result = render_pdf(load_pdf(pdf.tobytes()))
            self.assertNotIn("data-pdf-block=", result["html"])
            self.assertEqual(len(result["headings"]), 1)


if __name__ == "__main__":
    unittest.main()
