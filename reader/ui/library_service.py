"""Run every reading-library operation on one background thread.

A SQLite commit waits for the disk, and the library view checks whether each saved
file still exists; on a slow, busy or sleeping drive either can take seconds. The UI
thread therefore never touches the database. Operations run in submission order on a
single worker thread that owns the only connection. Each result returns to the UI
thread through a queued signal. After changes, one refreshed snapshot is published to
every window, however many changes were queued.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

from reader.library import ReadingLibrary

log = logging.getLogger(__name__)
EXPECTED_ERRORS = (sqlite3.Error, OSError, ValueError, TypeError)
UNAVAILABLE = "The document library is unavailable."

Operation = Callable[[ReadingLibrary], Any]
Done = Callable[[Any, str | None], None]


class LibraryService(QObject):
    """Serial, asynchronous access to the reading library shared by all windows."""

    changed = Signal(str)  # browser library JSON: availability, entries and categories
    _completed = Signal(object, object, object, bool)  # done, result, error, changed

    def __init__(self, path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.path = Path(path)
        self.error: str | None = None
        self.snapshot: str | None = None
        self._paths: frozenset[str] = frozenset()
        self._library: ReadingLibrary | None = None  # worker thread only
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="khana-library")
        self._lock = threading.Lock()
        self._pending = 0
        self._publish_queued = False
        self._workspace: tuple[tuple[str, ...], str | None] | None = None
        self._stopped = False
        self._completed.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        self._executor.submit(self._open)
        self.refresh()

    # ------------------------------------------------------------ UI thread API

    @property
    def available(self) -> bool:
        return self.error is None and not self._stopped

    def known(self, path: str) -> bool:
        """Whether the last published snapshot contains ``path``; never blocks."""
        return path in self._paths

    def submit(self, operation: Operation, done: Done | None = None, *, changes=False) -> None:
        """Run ``operation(library)`` on the worker; call ``done(result, error)`` here.

        ``changes`` publishes a fresh snapshot to every window after a success.
        """
        if self._stopped:
            if done:
                done(None, UNAVAILABLE)
            return
        with self._lock:
            self._pending += 1
        self._executor.submit(self._run, operation, done, changes)

    def refresh(self) -> None:
        """Publish a fresh snapshot (for example, when a saved file disappeared)."""
        if self._publish_queued or self._stopped:
            return
        self._publish_queued = True
        self.submit(self._read_snapshot, self._published)

    @property
    def workspace(self) -> tuple[tuple[str, ...], str | None] | None:
        """The open paths and active path most recently saved by this process."""
        return self._workspace

    def remember_workspace(self, paths: list[str], active: str | None) -> None:
        """Save the open document paths, skipping a write when nothing changed."""
        value = (tuple(dict.fromkeys(paths)), active)
        if value == self._workspace:
            return
        self._workspace = value
        self.submit(lambda library: library.save_workspace(*value), self._report)

    def flush(self, timeout: float = 10.0) -> None:
        """Wait for queued work, including follow-up work, and deliver every result.

        Tests use this; UI code must not, because it waits for the disk.
        """
        deadline = time.monotonic() + timeout
        while self._pending and not self._stopped:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The library worker did not finish in time.")
            self._executor.submit(lambda: None).result(timeout=remaining)
            QCoreApplication.processEvents()

    def blocking(self, operation: Operation) -> Any:
        """Run ``operation`` on the worker and wait. Tests only: it blocks the caller."""
        return self._executor.submit(lambda: operation(self._library)).result(timeout=10)

    def shutdown(self) -> None:
        """Finish queued writes before the application exits; later requests fail."""
        if self._stopped:
            return
        self._stopped = True
        self._executor.submit(self._close)
        self._executor.shutdown(wait=True)

    # ------------------------------------------------------------ worker thread

    def _open(self) -> None:
        try:
            self._library = ReadingLibrary(self.path)
        except (sqlite3.Error, OSError) as error:
            log.error("Reading library unavailable: %s", error)
            self.error = str(error)

    def _close(self) -> None:
        if self._library:
            self._library.connection.close()
            self._library = None

    def _run(self, operation: Operation, done: Done | None, changes: bool) -> None:
        result = error = None
        if self._library is None:
            error = f"{UNAVAILABLE} {self.error}" if self.error else UNAVAILABLE
        else:
            try:
                result = operation(self._library)
            except EXPECTED_ERRORS as caught:
                error = str(caught) or type(caught).__name__
            except Exception as caught:  # never let a bug kill the only worker
                log.exception("Library operation failed")
                error = f"Unexpected library error: {caught}"
        try:
            self._completed.emit(done, result, error, changes and error is None)
        except RuntimeError:  # the service was destroyed while the application exits
            pass

    def _read_snapshot(self, library: ReadingLibrary) -> dict:
        entries = library.entries()
        for entry in entries:
            entry["missing"] = not Path(entry["path"]).is_file()
        return {"available": True, "entries": entries, "categories": library.categories()}

    # ------------------------------------------------------------ delivery (UI thread)

    @Slot(object, object, object, bool)
    def _deliver(self, done: Done | None, result: Any, error: str | None, changed: bool) -> None:
        with self._lock:
            self._pending -= 1
        if changed:
            self.refresh()
        if done:
            try:
                done(result, error)
            except RuntimeError:  # the requesting window closed meanwhile
                log.debug("Library result for a closed window was dropped")

    def _published(self, snapshot: dict | None, error: str | None) -> None:
        self._publish_queued = False
        if snapshot is None:
            snapshot = {"available": False, "entries": [], "categories": [], "error": error}
        self._paths = frozenset(entry["path"] for entry in snapshot["entries"])
        self.snapshot = json.dumps(snapshot, ensure_ascii=False)
        self.changed.emit(self.snapshot)

    @staticmethod
    def _report(_result: Any, error: str | None) -> None:
        if error:
            log.warning("Could not remember the open documents: %s", error)
