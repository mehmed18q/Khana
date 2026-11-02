"""Schedule document work, coalesce previews and suppress results for closed tabs."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

from reader.ui.workers import FormatSourceTask, LoadTask, PdfPageTask, PreviewTask


@dataclass(frozen=True)
class PreviewRequest:
    source: str
    document_format: str
    folder: Path | None
    revision: int


class DocumentJobs(QObject):
    """One serial worker pool per window; all queue bookkeeping stays on Qt's UI thread."""

    loaded = Signal(str, str)
    loadFailed = Signal(str, str)
    busyChanged = Signal(bool)
    previewReady = Signal(str)
    previewFailed = Signal(str, int, str)
    sourceFormatted = Signal(str)
    pdfPageReady = Signal(str)

    def __init__(self, is_open: Callable[[str], bool], parent: QObject | None = None):
        super().__init__(parent)
        self._is_open = is_open
        self.stopped = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.loads: dict[str, LoadTask] = {}
        self.previews: dict[str, PreviewTask] = {}
        self.pending_previews: dict[str, PreviewRequest] = {}
        self.formats: dict[str, FormatSourceTask] = {}
        self.pdf_pages: dict[tuple[str, int, int], PdfPageTask] = {}

    def is_open(self, document_id: str) -> bool:
        return not self.stopped and self._is_open(document_id)

    def has_work(self, document_id: str) -> bool:
        """An in-flight worker reserves its ID until its completion is delivered."""
        return (
            document_id in self.previews
            or document_id in self.formats
            or any(key[0] == document_id for key in self.pdf_pages)
        )

    def load(self, path: Path, sample: bool = False) -> None:
        key = str(path)
        if self.stopped or key in self.loads:
            return
        task = LoadTask(path, sample)
        task.signals.finished.connect(self._loaded)
        task.signals.failed.connect(self._load_failed)
        self.loads[key] = task
        self.pool.start(task)
        self.busyChanged.emit(True)

    @Slot(str, str)
    def _loaded(self, path: str, payload: str) -> None:
        self.loads.pop(path, None)
        if not self.stopped:
            self.loaded.emit(path, payload)
            self.busyChanged.emit(bool(self.loads))

    @Slot(str, str)
    def _load_failed(self, path: str, message: str) -> None:
        self.loads.pop(path, None)
        if not self.stopped:
            self.loadFailed.emit(path, message)
            self.busyChanged.emit(bool(self.loads))

    def preview(self, document_id: str, request: PreviewRequest) -> None:
        if self.stopped:
            return
        self.pending_previews[document_id] = request
        self._start_preview(document_id)

    def _start_preview(self, document_id: str) -> None:
        if document_id in self.previews or document_id not in self.pending_previews:
            return
        request = self.pending_previews.pop(document_id)
        task = PreviewTask(
            document_id, request.source, request.document_format, request.folder, request.revision
        )
        self.previews[document_id] = task
        task.signals.finished.connect(self._preview_finished)
        task.signals.failed.connect(self._preview_failed)
        self.pool.start(task)

    @Slot(str, str)
    def _preview_finished(self, document_id: str, payload: str) -> None:
        self.previews.pop(document_id, None)
        if self.is_open(document_id):
            self.previewReady.emit(payload)
            self._start_preview(document_id)

    @Slot(str, str)
    def _preview_failed(self, document_id: str, message: str) -> None:
        task = self.previews.pop(document_id, None)
        if self.is_open(document_id) and task:
            self.previewFailed.emit(document_id, task.revision, message)
            self._start_preview(document_id)

    def format_source(self, document_id: str, source: str, document_format: str) -> None:
        if self.stopped or document_id in self.formats:
            return
        task = FormatSourceTask(document_id, source, document_format)
        task.signals.finished.connect(self._source_formatted)
        self.formats[document_id] = task
        self.pool.start(task)

    @Slot(str, str)
    def _source_formatted(self, document_id: str, result: str) -> None:
        self.formats.pop(document_id, None)
        if self.is_open(document_id):
            self.sourceFormatted.emit(result)

    def pdf_page(self, document_id: str, source: str, number: int, revision: int) -> None:
        key = (document_id, number, revision)
        if self.stopped or key in self.pdf_pages:
            return
        task = PdfPageTask(document_id, source, number, revision)
        self.pdf_pages[key] = task
        task.signals.finished.connect(self._pdf_finished)
        self.pool.start(task)

    @Slot(str, str)
    def _pdf_finished(self, document_id: str, payload: str) -> None:
        result = json.loads(payload)
        self.pdf_pages.pop((document_id, result["number"], result["revision"]), None)
        if self.is_open(document_id):
            self.pdfPageReady.emit(payload)

    def discard(self, document_id: str) -> None:
        self.pending_previews.pop(document_id, None)

    def shutdown(self) -> None:
        """Join workers before their QObject signal owners can be destroyed."""
        self.stopped = True
        self.pending_previews.clear()
        self.pool.waitForDone()
