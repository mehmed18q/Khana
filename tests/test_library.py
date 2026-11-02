import tempfile
import unittest
from pathlib import Path

from reader.library import ReadingLibrary, clean_anchor


def anchor(index=3):
    return {"index": index, "progress": 0.4, "text": "یک متن English", "hash": "abcdef", "tag": "p"}


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = str(self.base / "سند.md")
        Path(self.path).write_text("# Original source\n\nفارسی English")
        self.library = self.connect()
        self.library.remember(self.path, "Markdown")

    def connect(self):
        result = ReadingLibrary(self.base / "library.sqlite3")
        self.addCleanup(result.connection.close)
        return result

    def test_multiple_marks_notes_stars_and_session_survive_reopening(self):
        original = Path(self.path).read_bytes()
        first = self.library.save_annotation(self.path, "", "mark", "Chapter one", "", anchor())
        second = self.library.save_annotation(self.path, "", "mark", "Chapter two", "", anchor(8))
        note = self.library.save_annotation(
            self.path, "", "note", "یادداشت", "Line one\nنظر من <b>literal</b>", anchor(12)
        )
        self.library.set_starred(self.path, True)
        self.library.resume(self.path, first)
        self.library.save_workspace([self.path, self.path], self.path)
        reopened = self.connect()
        record = reopened.get(self.path)
        self.assertTrue(record["starred"])
        self.assertEqual([item["id"] for item in record["annotations"]], [first, second, note])
        self.assertEqual(record["resumeId"], first)
        self.assertEqual(record["annotations"][-1]["body"], "Line one\nنظر من <b>literal</b>")
        self.assertEqual(reopened.workspace(), {"paths": [self.path], "active": self.path})
        self.assertEqual(Path(self.path).read_bytes(), original)

    def test_edit_delete_and_resume_do_not_affect_other_annotations(self):
        first = self.library.save_annotation(self.path, "", "note", "Note", "Old", anchor())
        second = self.library.save_annotation(self.path, "", "mark", "Mark", "", anchor(9))
        self.library.save_annotation(self.path, first, "note", "Renamed", "Updated", anchor(99))
        record = self.library.get(self.path)
        self.assertEqual(record["annotations"][0]["anchor"]["index"], 3)
        self.assertEqual(record["annotations"][0]["body"], "Updated")
        self.library.delete_annotation(self.path, second)
        self.assertEqual(self.library.get(self.path)["resumeId"], first)
        self.library.delete_annotation(self.path, first)
        self.assertIsNone(self.connect().get(self.path)["resumeId"])
        self.assertEqual(self.library.get(self.path)["annotations"], [])

    def test_save_as_copies_annotations_without_moving_original(self):
        identifier = self.library.save_annotation(self.path, "", "note", "N", "Text", anchor())
        self.library.set_starred(self.path, True)
        target = str(self.base / "copy.md")
        self.library.remember(target, "Markdown", self.path)
        copied = self.library.get(target)
        self.assertTrue(copied["starred"])
        self.assertNotEqual(copied["annotations"][0]["id"], identifier)
        self.assertEqual(copied["resumeId"], copied["annotations"][0]["id"])
        self.library.delete_annotation(target, copied["resumeId"])
        self.assertEqual(len(self.library.get(self.path)["annotations"]), 1)
        # Saving again does not duplicate annotations or override destination choices.
        self.library.remember(target, "Markdown", self.path)
        self.assertEqual(self.library.get(target)["annotations"], [])

    def test_concurrent_connections_update_independent_fields(self):
        other = self.connect()
        self.library.set_starred(self.path, True)
        other.save_annotation(self.path, "", "note", "Other window", "hello", anchor())
        self.assertTrue(other.get(self.path)["starred"])
        self.assertEqual(len(self.library.get(self.path)["annotations"]), 1)

    def test_missing_files_keep_metadata_and_forget_never_deletes_source(self):
        self.library.save_annotation(self.path, "", "mark", "Place", "", anchor())
        Path(self.path).unlink()
        self.assertEqual(len(self.connect().get(self.path)["annotations"]), 1)
        Path(self.path).write_text("Restored")
        self.library.forget(self.path)
        self.assertIsNone(self.library.get(self.path))
        self.assertEqual(Path(self.path).read_text(), "Restored")
        self.assertEqual(
            self.library.connection.execute("SELECT count(*) FROM annotations").fetchone()[0], 0
        )

    def test_invalid_annotation_cannot_corrupt_existing_metadata(self):
        for malformed in [
            None,
            {},
            {"index": -1, "progress": 0.3},
            {"index": 1, "progress": float("nan")},
            {**anchor(), "quote": "x" * 501},
        ]:
            with self.assertRaises(ValueError):
                clean_anchor(malformed)
        for kind, label, body in [
            ("note", "name", ""),
            ("mark", "", ""),
            ("script", "name", "x"),
            ("note", "name", "x" * 10001),
        ]:
            with self.assertRaises(ValueError):
                self.library.save_annotation(self.path, "", kind, label, body, anchor())
        self.assertEqual(self.library.get(self.path)["annotations"], [])

    def test_get_reads_only_the_requested_document_and_annotations(self):
        other = str(self.base / "unrelated.md")
        self.library.remember(other, "Markdown")
        identifier = self.library.save_annotation(other, "", "mark", "Other", "", anchor())
        # An unrelated malformed anchor must not be parsed by this lookup.
        self.library.connection.execute(
            "UPDATE annotations SET anchor='invalid' WHERE id=?", (identifier,)
        )
        self.assertEqual(self.library.get(self.path)["path"], self.path)
        self.assertIsNone(self.library.get("unknown.md"))


if __name__ == "__main__":
    unittest.main()
