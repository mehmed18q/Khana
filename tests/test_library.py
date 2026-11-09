import sqlite3
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

    def test_pin_and_manual_order_survive_reopening_and_resaving(self):
        second, third = str(self.base / "second.md"), str(self.base / "third.md")
        self.library.remember(second, "Markdown")
        self.library.remember(third, "Markdown")
        self.library.move_relative(third, self.path, True)
        self.library.set_pinned(second, True)
        self.library.set_starred(third, True)
        self.library.remember(self.path, "Markdown")
        records = self.connect().entries()
        self.assertEqual([item["path"] for item in records], [second, third, self.path])
        self.assertTrue(records[0]["pinned"])
        self.assertTrue(records[1]["starred"])
        with self.assertRaises(ValueError):
            self.library.move_relative(third, second, True)
        self.library.set_pinned(second, False)
        self.assertEqual(
            [item["path"] for item in self.library.entries()], [third, self.path, second]
        )

    def test_reordering_visible_neighbors_keeps_hidden_files_in_order(self):
        paths = [str(self.base / f"item-{i}.md") for i in range(4)]
        for path in paths:
            self.library.remember(path, "Markdown")
        self.library.move_relative(paths[3], paths[0], True)
        self.assertEqual(
            [item["path"] for item in self.library.entries()],
            [self.path, paths[3], paths[0], paths[1], paths[2]],
        )
        self.library.move_relative(paths[3], paths[2], False)
        self.assertEqual([item["path"] for item in self.library.entries()], [self.path, *paths])

    def test_existing_library_migration_retains_stars_and_recent_order(self):
        database = self.base / "legacy.sqlite3"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE documents (path TEXT PRIMARY KEY, name TEXT NOT NULL, "
                "format TEXT NOT NULL, starred INTEGER NOT NULL DEFAULT 0, "
                "opened_at INTEGER NOT NULL, resume_id TEXT)"
            )
            connection.executemany(
                "INSERT INTO documents VALUES(?,?,'Markdown',?,?,NULL)",
                [("one.md", "one.md", 1, 1), ("two.md", "two.md", 0, 2)],
            )
        migrated = ReadingLibrary(database)
        self.addCleanup(migrated.connection.close)
        records = migrated.entries()
        self.assertEqual([item["path"] for item in records], ["two.md", "one.md"])
        self.assertTrue(records[1]["starred"])
        self.assertFalse(any(item["pinned"] for item in records))
        self.assertTrue(all(item["categoryId"] == "" for item in records))

    def test_categories_group_unrelated_paths_and_persist_names_and_order(self):
        other = str(self.base / "another folder" / "other.md")
        Path(other).parent.mkdir()
        Path(other).write_text("Other source")
        self.library.remember(other, "Markdown")
        first = self.library.create_category("مطالعه", [self.path, other])
        second = self.library.create_category("Work")
        self.library.rename_category(second, "کار و پروژه")
        self.library.move_category(second, first, True)
        self.library.move_relative(other, self.path, True)
        self.library.collapse_category(first, "library", True)
        reopened = self.connect()
        self.assertEqual([c["name"] for c in reopened.categories()], ["کار و پروژه", "مطالعه"])
        self.assertEqual([e["path"] for e in reopened.entries()], [other, self.path])
        self.assertTrue(all(e["categoryId"] == first for e in reopened.entries()))
        self.assertTrue(reopened.categories()[1]["libraryCollapsed"])
        self.assertFalse(reopened.categories()[1]["filesCollapsed"])
        self.assertEqual(Path(other).read_text(), "Other source")
        self.assertTrue(Path(self.path).is_file())

    def test_invalid_batch_category_move_is_atomic_and_delete_keeps_documents(self):
        note = self.library.save_annotation(self.path, "", "note", "Keep", "My note", anchor())
        category = self.library.create_category("Reading", [self.path])
        for action in (
            lambda: self.library.assign_category([self.path, "unknown.md"], ""),
            lambda: self.library.assign_category([self.path], "missing-category"),
            lambda: self.library.create_category("Should roll back", ["unknown.md"]),
            lambda: self.library.create_category(" reading "),
            lambda: self.library.create_category("\ninvalid"),
        ):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(len(self.library.categories()), 1)
        self.assertEqual(self.library.get(self.path)["categoryId"], category)
        self.library.delete_category(category)
        record = self.library.get(self.path)
        self.assertEqual(record["categoryId"], "")
        self.assertEqual(record["annotations"][0]["id"], note)
        self.assertTrue(Path(self.path).is_file())

    def test_category_order_precedes_pins_and_reorder_stays_within_category(self):
        other = str(self.base / "other.md")
        self.library.remember(other, "Markdown")
        category = self.library.create_category("Group", [self.path])
        self.library.set_pinned(other, True)
        self.assertEqual([e["path"] for e in self.library.entries()], [self.path, other])
        self.library.set_pinned(other, False)
        with self.assertRaises(ValueError):
            self.library.move_relative(other, self.path, True)
        self.library.assign_category([other], category)
        self.library.move_relative(other, self.path, True)
        self.assertEqual([e["path"] for e in self.library.entries()], [other, self.path])

    def test_failed_file_rename_rolls_back_metadata_and_workspace(self):
        category = self.library.create_category("Group", [self.path])
        note = self.library.save_annotation(self.path, "", "note", "Keep", "My note", anchor())
        self.library.save_workspace([self.path], self.path)
        target = str(self.base / "renamed.md")

        def fail():
            raise OSError("Permission denied")

        with self.assertRaises(OSError):
            self.library.rename_document(self.path, target, fail)
        self.assertIsNone(self.library.get(target))
        self.assertEqual(self.library.get(self.path)["categoryId"], category)
        self.assertEqual(self.library.get(self.path)["annotations"][0]["id"], note)
        self.assertEqual(self.library.workspace(), {"paths": [self.path], "active": self.path})


if __name__ == "__main__":
    unittest.main()
