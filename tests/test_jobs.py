"""Exercise queue policy deterministically without worker threads or a desktop."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from reader.ui.jobs import DocumentJobs, PreviewRequest


class DocumentJobsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.open_documents = {"doc"}
        self.jobs = DocumentJobs(self.open_documents.__contains__)
        start = patch.object(self.jobs.pool, "start")
        self.start = start.start()
        self.addCleanup(start.stop)
        self.addCleanup(self.jobs.shutdown)

    def preview(self, revision):
        self.jobs.preview("doc", PreviewRequest(f"source {revision}", "Markdown", None, revision))

    def test_preview_coalesces_to_latest_snapshot(self):
        received = []
        self.jobs.previewReady.connect(received.append)
        self.preview(1)
        first = self.start.call_args.args[0]
        self.preview(2)
        self.preview(3)
        self.assertEqual(self.start.call_count, 1)
        first.signals.finished.emit("doc", "first preview")
        latest = self.start.call_args.args[0]
        self.assertEqual((latest.source, latest.revision), ("source 3", 3))
        latest.signals.finished.emit("doc", "latest preview")
        self.assertEqual(received, ["first preview", "latest preview"])
        self.assertFalse(self.jobs.pending_previews)

    def test_failed_preview_does_not_block_latest_edit(self):
        errors = []
        self.jobs.previewFailed.connect(lambda *args: errors.append(args))
        self.preview(1)
        first = self.start.call_args.args[0]
        self.preview(2)
        first.signals.failed.emit("doc", "invalid source")
        self.assertEqual(errors, [("doc", 1, "invalid source")])
        self.assertEqual(self.start.call_args.args[0].revision, 2)

    def test_closing_document_discards_queued_preview_and_late_result(self):
        received = []
        self.jobs.previewReady.connect(received.append)
        self.preview(1)
        first = self.start.call_args.args[0]
        self.preview(2)
        self.open_documents.clear()
        self.jobs.discard("doc")
        first.signals.finished.emit("doc", "too late")
        self.assertEqual(received, [])
        self.assertEqual(self.start.call_count, 1)
        self.assertFalse(self.jobs.pending_previews)

    def test_loading_reserves_path_until_completion_and_tracks_busy_state(self):
        busy, reservations_at_delivery = [], []
        self.jobs.busyChanged.connect(busy.append)
        self.jobs.loaded.connect(
            lambda path, payload: reservations_at_delivery.append(path in self.jobs.loads)
        )
        path = Path("/tmp/khana-jobs-first.md")
        self.jobs.load(path)
        first = self.start.call_args.args[0]
        self.jobs.load(path)
        self.jobs.load(Path("/tmp/khana-jobs-second.md"))
        second = self.start.call_args.args[0]
        self.assertEqual(self.start.call_count, 2)
        first.signals.finished.emit(str(path), "document")
        self.assertEqual(reservations_at_delivery, [False])
        self.assertTrue(busy[-1])
        second.signals.failed.emit(str(second.path), "missing")
        self.assertFalse(busy[-1])
        self.assertFalse(self.jobs.loads)

    def test_pdf_requests_deduplicate_by_document_page_and_revision(self):
        received = []
        self.jobs.pdfPageReady.connect(received.append)
        self.jobs.pdf_page("doc", "source", 0, 1)
        first = self.start.call_args.args[0]
        self.jobs.pdf_page("doc", "source", 0, 1)
        self.jobs.pdf_page("doc", "new source", 0, 2)
        self.assertEqual(self.start.call_count, 2)
        first.signals.finished.emit("doc", json.dumps({"number": 0, "revision": 1, "url": "image"}))
        self.assertNotIn(("doc", 0, 1), self.jobs.pdf_pages)
        self.assertIn(("doc", 0, 2), self.jobs.pdf_pages)
        self.assertEqual(len(received), 1)

    def test_closed_document_receives_neither_pdf_nor_format_results(self):
        received = []
        self.jobs.pdfPageReady.connect(received.append)
        self.jobs.sourceFormatted.connect(received.append)
        self.jobs.pdf_page("doc", "source", 0, 1)
        pdf = self.start.call_args.args[0]
        self.jobs.format_source("doc", "source", "JSON")
        formatting = self.start.call_args.args[0]
        self.open_documents.clear()
        self.jobs.discard("doc")
        pdf.signals.finished.emit("doc", json.dumps({"number": 0, "revision": 1, "url": "image"}))
        formatting.signals.finished.emit("doc", "formatted")
        self.assertEqual(received, [])
        self.assertFalse(self.jobs.pdf_pages)
        self.assertFalse(self.jobs.formats)

    def test_shutdown_suppresses_already_queued_completion_signals(self):
        received = []
        self.jobs.loaded.connect(lambda path, payload: received.append(payload))
        self.jobs.previewReady.connect(received.append)
        self.jobs.load(Path("/tmp/khana-shutdown.md"))
        load = self.start.call_args.args[0]
        self.preview(1)
        preview = self.start.call_args.args[0]
        self.jobs.shutdown()
        load.signals.finished.emit(str(load.path), "late load")
        preview.signals.finished.emit("doc", "late preview")
        self.assertEqual(received, [])

    def test_shutdown_rejects_late_commands(self):
        self.jobs.shutdown()
        self.jobs.load(Path("/tmp/khana-shutdown.md"))
        self.preview(1)
        self.jobs.pdf_page("doc", "source", 0, 1)
        self.jobs.format_source("doc", "source", "JSON")
        self.start.assert_not_called()
        self.assertFalse(self.jobs.pending_previews)
