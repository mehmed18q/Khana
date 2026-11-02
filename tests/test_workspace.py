"""Cross-window ownership and library regressions without a graphical desktop."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QObject

from reader.documents import load_document
from reader.editing import EditSession
from reader.ui.bridge import Bridge
from reader.ui.window import ReaderWindow
from reader.ui.workspace import TabTransfer, WindowManager


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / "shared.md"
        self.path.write_text("# Shared document\n")
        self.manager = WindowManager(self.folder / "settings.ini", window_factory=ReaderWindow)
        self.origin, self.other = self.window(), self.window()

    def window(self):
        window = QObject()
        window.manager = self.manager
        window.restore_session = False
        window.bridge = Bridge(window, [], self.manager.settings_path)
        window.bridge.initialized = True
        self.manager.windows.append(window)
        self.addCleanup(window.bridge.library.connection.close)
        return window

    def opened(self, window):
        session = EditSession.opened(load_document(self.path))
        window.bridge.sessions[session.document.id] = session
        window.bridge.library.remember(str(self.path), "Markdown")
        return session

    def test_library_updates_reach_every_window(self):
        self.opened(self.origin)
        received = []
        self.other.bridge.libraryChanged.connect(received.append)
        self.origin.bridge.starDocument(str(self.path), True)
        self.assertTrue(received, "The other window still shows the old star state")
        self.assertTrue(json.loads(received[-1])["entries"][0]["starred"])

    def test_cannot_forget_a_document_open_in_another_window(self):
        self.opened(self.origin)
        library = self.origin.bridge.library
        annotation = library.save_annotation(
            str(self.path), "", "note", "Keep me", "Text", {"index": 0, "progress": 0}
        )
        self.other.bridge.forgetDocument(str(self.path))
        record = library.get(str(self.path))
        self.assertIsNotNone(
            record, "Removing from a different window deleted an open document and its notes"
        )
        self.assertEqual(record["annotations"][0]["id"], annotation)

    def test_pending_open_is_not_duplicated_in_another_window(self):
        with (
            patch.object(self.origin.bridge.jobs.pool, "start") as first,
            patch.object(self.other.bridge.jobs.pool, "start") as second,
            patch.object(self.manager, "reveal"),
        ):
            self.origin.bridge.load_paths([self.path])
            self.other.bridge.load_paths([self.path])
        self.assertEqual(first.call_count + second.call_count, 1)
        self.assertNotIn(str(self.path), self.other.bridge.jobs.loads)

    def test_save_as_cannot_replace_a_file_loading_in_another_window(self):
        self.other.bridge.newDocument("Markdown")
        draft = next(iter(self.other.bridge.sessions.values()))
        draft.document.source = "# Replacement"
        self.origin.bridge.jobs.loads[str(self.path)] = object()
        with (
            patch(
                "reader.ui.bridge.QFileDialog.getSaveFileName",
                return_value=(str(self.path), "Markdown"),
            ),
            patch.object(self.other.bridge, "_ask") as ask,
        ):
            self.assertFalse(self.other.bridge._save_session(draft, save_as=True))
        ask.assert_not_called()
        self.assertEqual(self.path.read_text(), "# Shared document\n")

    def test_save_and_reload_cannot_mutate_a_transferring_buffer(self):
        session = self.opened(self.origin)
        self.manager.transfers[self.other, session.document.id] = TabTransfer(
            self.origin, session.document.id
        )
        with (
            patch.object(self.origin.bridge, "_save_session") as save,
            patch.object(self.origin.bridge, "_confirm_changes", return_value=False),
            patch("reader.ui.bridge.load_document") as reload,
        ):
            self.origin.bridge.saveDocument(session.document.id, "# Changed during transfer", True)
            self.origin.bridge.reloadFile(session.document.id, "# Changed during transfer")
        save.assert_not_called()
        reload.assert_not_called()
        self.assertEqual(session.document.source, "# Shared document\n")

    def test_early_acknowledgment_does_not_remove_origin(self):
        session = self.opened(self.origin)
        key = self.other, session.document.id
        self.manager.transfers[key] = TabTransfer(self.origin, session.document.id)
        self.manager.finish_transfer(*key)
        self.assertIn(session.document.id, self.origin.bridge.sessions)
        self.assertIn(key, self.manager.transfers)

    def test_reopening_does_not_receive_results_from_previous_session(self):
        bridge = self.origin.bridge
        for job in ("preview", "format", "pdf"):
            with self.subTest(job=job), patch.object(bridge.jobs.pool, "start"):
                previous = self.opened(self.origin).document
                if job == "preview":
                    bridge.previewDocument(previous.id, previous.source, 1)
                    task = bridge.jobs.previews[previous.id]
                elif job == "format":
                    bridge.formatSource(previous.id, previous.source)
                    task = bridge.jobs.formats[previous.id]
                else:
                    bridge.jobs.pdf_page(previous.id, previous.source, 0, 1)
                    task = bridge.jobs.pdf_pages[previous.id, 0, 1]
                bridge.release_session(previous.id)
                bridge._loaded(str(self.path), json.dumps(previous.to_dict()))
                self.assertNotIn(previous.id, bridge.sessions)
                received = []
                bridge.jobs.pdfPageReady.connect(received.append)
                bridge.jobs.sourceFormatted.connect(received.append)
                bridge.jobs.previewReady.connect(received.append)
                task.signals.finished.emit(previous.id, json.dumps({"number": 0, "revision": 1}))
                self.assertEqual(received, [])
                bridge.sessions.clear()

    def test_aborting_delivered_transfer_keeps_original_buffer(self):
        session = self.opened(self.origin)
        key = self.other, session.document.id
        self.manager.transfers[key] = TabTransfer(self.origin, session.document.id, session=session)
        self.manager.deliver_transfer(self.other)
        self.manager.abort_transfer(*key)
        self.assertIs(self.origin.bridge.sessions[session.document.id], session)
        self.assertNotIn(session.document.id, self.other.bridge.sessions)
        self.assertNotIn(key, self.manager.transfers)


if __name__ == "__main__":
    unittest.main()
