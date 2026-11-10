"""Worker-thread operations; only immutable snapshots and signals cross threads."""

import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from reader.diagnostics import measured
from reader.documents import load_document, render_source


class LoadSignals(QObject):
    finished = Signal(str, str)
    failed = Signal(str, str)


class LoadTask(QRunnable):
    def __init__(self, path: Path, sample=False):
        super().__init__()
        self.path = path
        self.sample = sample
        self.signals = LoadSignals()

    @measured("load")
    def run(self):
        try:
            document = load_document(self.path, sample=self.sample)
            self.signals.finished.emit(
                str(self.path), json.dumps(document.to_dict(), ensure_ascii=False)
            )
        except (OSError, ValueError) as error:
            logging.getLogger(__name__).exception("Could not load %s", self.path)
            if isinstance(error, FileNotFoundError):
                message = "File not found. It may have been moved or deleted."
            elif isinstance(error, PermissionError):
                message = "You do not have permission to read this file."
            else:
                message = str(error)
            self.signals.failed.emit(str(self.path), message)
        except Exception:
            logging.getLogger(__name__).exception("Could not load %s", self.path)
            self.signals.failed.emit(str(self.path), "This file could not be read.")


class PdfPageTask(QRunnable):
    def __init__(self, document_id, source, number, revision):
        super().__init__()
        self.document_id, self.source, self.number, self.revision = (
            document_id,
            source,
            number,
            revision,
        )
        self.signals = LoadSignals()

    @measured("pdf-page")
    def run(self):
        from reader.pdf_documents import page_image

        payload = {"id": self.document_id, "number": self.number, "revision": self.revision}
        try:
            payload["url"] = page_image(self.source, self.number)
        except Exception as error:
            logging.getLogger(__name__).exception(
                "PDF page failed document=%s page=%s", self.document_id, self.number
            )
            payload["error"] = str(error)
        self.signals.finished.emit(self.document_id, json.dumps(payload))


class PreviewTask(QRunnable):
    def __init__(self, document_id, source, document_format, folder, revision):
        super().__init__()
        self.document_id, self.source = document_id, source
        self.document_format, self.folder, self.revision = document_format, folder, revision
        self.signals = LoadSignals()

    @measured("preview")
    def run(self):
        try:
            rendered = render_source(self.source, self.document_format, self.folder)
            self.signals.finished.emit(
                self.document_id,
                json.dumps(
                    {"id": self.document_id, "revision": self.revision, **rendered},
                    ensure_ascii=False,
                ),
            )
        except Exception as error:
            logging.getLogger(__name__).exception("Preview failed document=%s", self.document_id)
            self.signals.failed.emit(self.document_id, str(error))


class FormatSourceTask(QRunnable):
    def __init__(self, document_id, source, document_format):
        super().__init__()
        self.document_id, self.source, self.document_format = document_id, source, document_format
        self.signals = LoadSignals()

    @measured("format")
    def run(self):
        result = {"id": self.document_id}
        try:
            from reader.source_formatting import beautify_source

            result["source"] = beautify_source(self.source, self.document_format)
        except Exception as error:
            logging.getLogger(__name__).exception("Formatting failed document=%s", self.document_id)
            result["error"] = f"Could not format {self.document_format}: {str(error)[:500]}"
        self.signals.finished.emit(self.document_id, json.dumps(result, ensure_ascii=False))
