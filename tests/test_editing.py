import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reader.documents import MAX_FILE_BYTES, Document, load_document
from reader.editing import EditSession, FileChangedError, fingerprint


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)

    def session(self, text="# Original\n\nسلام", name="note.md"):
        path = self.base / name
        path.write_text(text, encoding="utf-8")
        return EditSession.opened(load_document(path)), path

    def test_save_preserves_unsanitized_html_source(self):
        session, path = self.session(
            "<html><head><style>p{color:red}</style></head><body><p>سلام</p><script>test()</script></body></html>",
            "note.html",
        )
        session.document.source = session.document.source.replace("سلام", "سلام English")
        self.assertNotIn("<script>", session.document.html)
        session.save(path, session.document.fingerprint)
        self.assertIn("<script>test()</script>", path.read_text())
        self.assertIn("<style>", path.read_text())
        self.assertFalse(session.dirty)

    def test_encoding_bom_and_newlines_are_preserved(self):
        for codec, bom in [
            ("utf-8", b""),
            ("utf-8", b"\xef\xbb\xbf"),
            ("utf-16-le", b"\xff\xfe"),
            ("utf-16-be", b"\xfe\xff"),
        ]:
            with self.subTest(codec=codec, bom=bom):
                path = self.base / "unicode.md"
                path.write_bytes(bom + "# سلام\r\n\r\nEnglish\r\n".encode(codec))
                session = EditSession.opened(load_document(path))
                session.document.source += "خط تازه\n"
                session.save(path, session.document.fingerprint)
                self.assertEqual(
                    path.read_bytes(), bom + "# سلام\r\n\r\nEnglish\r\nخط تازه\r\n".encode(codec)
                )

    def test_save_as_changes_path_only_after_success(self):
        session, old = self.session()
        identity = session.document.id
        original = old.read_bytes()
        session.document.source = "# Copy\n"
        target = self.base / "copy.md"
        session.save(target, None)
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual(target.read_text(), "# Copy\n")
        self.assertEqual(session.document.id, identity)
        self.assertEqual(session.document.path, str(target))

    def test_external_changes_are_not_overwritten(self):
        session, path = self.session()
        session.document.source = "# My edits"
        path.write_text("Other application", encoding="utf-8")
        with self.assertRaises(FileChangedError):
            session.save(path, session.document.fingerprint)
        self.assertEqual(path.read_text(), "Other application")
        self.assertTrue(session.dirty)

    def test_change_during_save_cancels_atomic_commit(self):
        session, path = self.session()
        expected = session.document.fingerprint
        session.document.source = "My edits"
        count = 0

        def concurrent_fingerprint(target):
            nonlocal count
            count += 1
            if count == 2:
                target.write_text("External edit", encoding="utf-8")
            return fingerprint(target)

        with patch("reader.editing.fingerprint", side_effect=concurrent_fingerprint):
            with self.assertRaises(FileChangedError):
                session.save(path, expected)
        self.assertEqual(path.read_text(), "External edit")
        self.assertTrue(session.dirty)

    def test_write_failure_keeps_original_and_dirty_state(self):
        session, path = self.session()
        original = path.read_bytes()
        session.document.source = "New content"
        with patch("reader.editing.QSaveFile") as writer:
            writer.return_value.open.return_value = True
            writer.return_value.write.return_value = -1
            writer.return_value.errorString.return_value = "Disk is full"
            with self.assertRaises(OSError):
                session.save(path, session.document.fingerprint)
            writer.return_value.cancelWriting.assert_called_once()
            writer.return_value.commit.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(session.dirty)

    def test_wrong_format_and_oversize_leave_target_intact(self):
        session, path = self.session()
        original = path.read_bytes()
        with self.assertRaises(ValueError):
            session.save(self.base / "wrong.html", None)
        session.document.source = "a" * (MAX_FILE_BYTES + 1)
        with self.assertRaises(ValueError):
            session.save(path, session.document.fingerprint)
        self.assertEqual(path.read_bytes(), original)

    def test_new_empty_document_can_be_saved(self):
        document = Document("untitled:test", "Untitled.md", "", "", [], 0, 0, "UTF-8")
        session = EditSession.opened(document)
        path = self.base / "empty.md"
        session.save(path, None)
        self.assertEqual(path.read_bytes(), b"")
        self.assertEqual(document.path, str(path))


if __name__ == "__main__":
    unittest.main()
