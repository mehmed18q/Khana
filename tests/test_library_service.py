"""The reading library runs on its own thread and reports back on the UI thread."""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from reader.library import ReadingLibrary
from reader.ui.library_service import LibraryService


class LibraryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.document = self.folder / "doc.md"
        self.document.write_text("# Document\n")
        self.service = LibraryService(self.folder / "library.sqlite3")
        self.addCleanup(self.service.shutdown)
        self.service.flush()

    def test_operations_run_off_the_ui_thread_in_order_and_reply_on_it(self):
        threads, replies = [], []

        def operation(library, value):
            threads.append(threading.current_thread())
            library.remember(str(self.document), "Markdown")
            return value

        for value in range(5):
            self.service.submit(
                lambda library, value=value: operation(library, value),
                lambda result, error: replies.append((result, error, threading.current_thread())),
                changes=True,
            )
        self.assertEqual(replies, [], "Results must arrive later, through the event loop")
        self.service.flush()
        self.assertTrue(all(thread is not threading.main_thread() for thread in threads))
        self.assertEqual([result for result, _, _ in replies], [0, 1, 2, 3, 4])
        self.assertTrue(all(error is None for _, error, _ in replies))
        self.assertTrue(all(thread is threading.main_thread() for _, _, thread in replies))

    def test_changes_publish_one_snapshot_with_missing_files(self):
        published = []
        self.service.changed.connect(published.append)
        for name in ("doc.md", "gone.md"):
            path = str(self.folder / name)
            self.service.submit(
                lambda library, p=path: library.remember(p, "Markdown"), changes=True
            )
        self.service.flush()
        self.assertEqual(len(published), 1, "Queued changes share one refreshed snapshot")
        snapshot = json.loads(published[-1])
        missing = {Path(entry["path"]).name: entry["missing"] for entry in snapshot["entries"]}
        self.assertEqual(missing, {"doc.md": False, "gone.md": True})
        self.assertTrue(self.service.known(str(self.document)))

    def test_errors_are_returned_instead_of_raised(self):
        replies = []
        self.service.submit(
            lambda library: library.create_category(""), lambda *reply: replies.append(reply)
        )
        self.service.flush()
        self.assertIsNone(replies[0][0])
        self.assertIn("category name", replies[0][1])

    def test_unchanged_workspace_is_not_written_again(self):
        statements = []
        self.service.blocking(
            lambda library: library.connection.set_trace_callback(statements.append)
        )
        for _ in range(3):
            self.service.remember_workspace([str(self.document)], str(self.document))
        self.service.flush()
        self.assertEqual(sum("workspace" in statement for statement in statements), 1)

    def test_shutdown_finishes_queued_writes(self):
        self.service.submit(lambda library: library.remember(str(self.document), "Markdown"))
        self.service.shutdown()
        replies = []
        self.service.submit(lambda library: None, lambda *reply: replies.append(reply))
        self.assertEqual(replies[0][1], "The document library is unavailable.")
        library = ReadingLibrary(self.folder / "library.sqlite3")
        self.addCleanup(library.connection.close)
        self.assertIsNotNone(library.get(str(self.document)))

    def test_an_unreadable_database_reports_unavailable(self):
        broken = self.folder / "broken"
        broken.mkdir()
        service = LibraryService(broken)  # a directory cannot be opened as a database
        self.addCleanup(service.shutdown)
        replies = []
        service.submit(lambda library: None, lambda *reply: replies.append(reply))
        service.flush()
        self.assertFalse(service.available)
        self.assertIn("unavailable", replies[0][1])
        self.assertFalse(json.loads(service.snapshot)["available"])


if __name__ == "__main__":
    unittest.main()
