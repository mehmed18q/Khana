"""Explicit WebChannel commands coordinating document sessions and native UI."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

from PySide6.QtCore import QMimeData, QObject, QSettings, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCursor, QDesktopServices, QDrag
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from reader import APP_NAME
from reader.api_requests import ApiRequests
from reader.documents import (
    EXTENSIONS,
    FORMAT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    Document,
    file_filter,
    load_document,
)
from reader.editing import EditSession, fingerprint
from reader.library import ReadingLibrary
from reader.preferences import normalize_preferences
from reader.resources import SAMPLE
from reader.ui.jobs import DocumentJobs, PreviewRequest
from reader.ui.settings import default_settings_path


class Bridge(QObject):
    documentLoaded = Signal(str)
    documentSaved = Signal(str)
    documentClosed = Signal(str)
    documentActivated = Signal(str)
    previewReady = Signal(str)
    previewFailed = Signal(str, int, str)
    errorOccurred = Signal(str)
    busyChanged = Signal(bool)
    settingsLoaded = Signal(str)
    libraryChanged = Signal(str)
    pdfPageReady = Signal(str)
    sourceFormatted = Signal(str)
    apiResponse = Signal(str)
    command = Signal(str)

    def __init__(self, window, initial_paths, settings_path=None):
        super().__init__(window)
        self.window = window
        self.initial_paths = initial_paths
        self.settings = QSettings(
            str(settings_path or default_settings_path()), QSettings.Format.IniFormat
        )
        self.library_error = None
        try:
            self.library = ReadingLibrary(
                Path(self.settings.fileName()).with_name("library.sqlite3")
            )
        except (OSError, sqlite3.Error) as error:
            self.library = None
            self.library_error = str(error)
        self.active_id = None
        self.restoring = False
        self.restore_active = None
        self.sessions: dict[str, EditSession] = {}
        self.new_count = 0
        self.jobs = DocumentJobs(lambda identifier: identifier in self.sessions, self)
        self.jobs.loaded.connect(self._loaded)
        self.jobs.loadFailed.connect(self._failed)
        self.jobs.busyChanged.connect(self.busyChanged)
        self.jobs.previewReady.connect(self.previewReady)
        self.jobs.previewFailed.connect(self.previewFailed)
        self.jobs.sourceFormatted.connect(self.sourceFormatted)
        self.jobs.pdfPageReady.connect(self.pdfPageReady)
        self.initialized = False
        self.api_requests = ApiRequests(self)
        self.api_requests.finished.connect(self.apiResponse)

    @Slot(str, str, str)
    def executeApiRequest(self, document_id, request_id, raw):
        session = self.sessions.get(document_id)
        if not session or session.document.format not in {"JSON", "YAML"}:
            self.api_requests.fail(
                document_id, request_id, "Open the API document before sending a request."
            )
            return
        self.api_requests.send(document_id, request_id, raw)

    @Slot(str)
    def cancelApiRequests(self, document_id):
        self.api_requests.cancel(document_id)

    @Slot()
    def ready(self):
        if self.initialized:
            return
        self.initialized = True
        try:
            preferences = json.loads(str(self.settings.value("reading", "{}")))
        except ValueError:
            preferences = {}
        self.settingsLoaded.emit(json.dumps(normalize_preferences(preferences)))
        entries = self.publish_library()
        if self.library_error:
            self.errorOccurred.emit(f"Reading library unavailable: {self.library_error}")
        if not self.window.restore_session:
            self.command.emit("empty")
            self.window.manager.deliver_transfer(self.window)
            if self.initial_paths:
                self.load_paths(self.initial_paths)
            return
        workspace = {"paths": [], "active": None}
        if self.library:
            try:
                workspace = self.library.workspace()
            except (sqlite3.Error, ValueError) as error:
                self.errorOccurred.emit(f"Could not restore the reading session: {error}")
        paths = [Path(path) for path in workspace["paths"] if Path(path).is_file()]
        paths += [
            Path(path).resolve() for path in self.initial_paths if Path(path).resolve() not in paths
        ]
        self.restore_active = (
            str(Path(self.initial_paths[-1]).resolve())
            if self.initial_paths
            else workspace["active"]
        )
        if paths:
            self.restoring = True
            self.load_paths(paths)
        elif entries == []:
            self.load_paths([SAMPLE], sample=True)
        else:
            self.command.emit("empty")

    def publish_library(self):
        try:
            entries = self.library.entries() if self.library else []
            for entry in entries:
                entry["missing"] = not Path(entry["path"]).is_file()
            self.libraryChanged.emit(
                json.dumps(
                    {"available": self.library is not None, "entries": entries}, ensure_ascii=False
                )
            )
            return entries
        except (sqlite3.Error, ValueError) as error:
            self.errorOccurred.emit(f"Could not read the document library: {error}")

    def _library_change(self, method, *args):
        if not self.library:
            return False
        try:
            getattr(self.library, method)(*args)
            for window in self.window.manager.windows:
                window.bridge.publish_library()
            return True
        except (sqlite3.Error, OSError, ValueError) as error:
            self.errorOccurred.emit(f"Could not save reading information: {error}")
            return False

    def remember_workspace(self):
        if self.restoring or not self.library:
            return
        sessions = (s for w in self.window.manager.windows for s in w.bridge.sessions.values())
        paths = list(
            dict.fromkeys(
                s.document.path for s in sessions if s.document.path and not s.document.sample
            )
        )
        active = self.sessions.get(self.active_id)
        active_path = active.document.path if active and active.document.path in paths else None
        try:
            self.library.save_workspace(paths, active_path)
        except (sqlite3.Error, OSError) as error:
            self.errorOccurred.emit(f"Could not remember the open documents: {error}")

    def _finish_restore(self):
        if self.restoring and not self.jobs.loads:
            self.restoring = False
            self.active_id = next(
                (
                    s.document.id
                    for s in self.sessions.values()
                    if s.document.path == self.restore_active
                ),
                next(reversed(self.sessions), None),
            )
            if self.active_id:
                self.documentActivated.emit(self.active_id)
            else:
                self.command.emit("empty")
            self.remember_workspace()

    @Slot(str)
    def activateDocument(self, document_id):
        if document_id in self.sessions and not self.restoring:
            self.active_id = document_id
            self.remember_workspace()

    @Slot(str)
    def openLibrary(self, path):
        if not self.library:
            return
        try:
            if not self.library.get(path):
                return
        except (sqlite3.Error, ValueError) as error:
            self.errorOccurred.emit(f"Could not read the document library: {error}")
            return
        existing = next(
            (s.document.id for s in self.sessions.values() if s.document.path == path), None
        )
        self.load_paths([Path(path)])
        if existing:
            self.command.emit("resume-annotation")

    @Slot(str, bool)
    def starDocument(self, path, starred):
        self._library_change("set_starred", path, starred)

    @Slot(str)
    def forgetDocument(self, path):
        if self.window.manager.path_owner(path):
            self.errorOccurred.emit("Close the document before removing it from the library.")
            return
        if self._library_change("forget", path):
            self.remember_workspace()

    @Slot(str, str, str, result=bool)
    def saveAnnotation(self, document_id, source, raw):
        session = self.sync_source(document_id, source)
        if not session or not session.document.path or session.document.sample:
            self.errorOccurred.emit("Save this document before adding marks or notes.")
            return False
        try:
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise ValueError("Invalid annotation.")
            if not item.get("id") and session.dirty:
                raise ValueError("Save your document changes before adding a mark or note.")
            anchor = item.get("anchor")
            if isinstance(anchor, dict) and not item.get("id"):
                anchor["fingerprint"] = session.document.fingerprint
            return self._library_change(
                "save_annotation",
                session.document.path,
                item.get("id"),
                item.get("kind"),
                item.get("label"),
                item.get("body", ""),
                anchor,
            )
        except (ValueError, TypeError) as error:
            self.errorOccurred.emit(str(error))
            return False

    @Slot(str, str)
    def deleteAnnotation(self, path, identifier):
        self._library_change("delete_annotation", path, identifier)

    @Slot(str, str)
    def resumeAnnotation(self, path, identifier):
        self._library_change("resume", path, identifier)

    @Slot()
    def openFiles(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.window,
            "Open a document",
            str(self.settings.value("lastFolder", Path.home())),
            "Documents ("
            + " ".join(
                "*" + ext for ext in sorted(EXTENSIONS | {ext.upper() for ext in EXTENSIONS})
            )
            + ");;"
            + ";;".join(file_filter(name) for name in FORMAT_EXTENSIONS)
            + ";;All files (*)",
        )
        if paths:
            self.settings.setValue("lastFolder", str(Path(paths[0]).parent))
            self.load_paths([Path(p) for p in paths])

    def load_paths(self, paths, sample=False):
        for path in paths:
            path = path.expanduser().resolve()
            key = str(path)
            existing = next(
                (s.document.id for s in self.sessions.values() if s.document.path == key), None
            )
            if existing:
                self.active_id = existing
                self.documentActivated.emit(existing)
                self.remember_workspace()
                continue
            owner = self.window.manager.path_owner(key, exclude=self.window)
            if owner:
                if owner.bridge.initialized:
                    owner.bridge.load_paths([path], sample)
                self.window.manager.reveal(owner)
                continue
            self.jobs.load(path, sample)

    @Slot(str, str)
    def _loaded(self, path, payload):
        document = Document(**json.loads(payload))
        if document.id in self.sessions or self.jobs.has_work(document.id):
            document.id = f"{uuid4()}:{path}"
        self.sessions[document.id] = EditSession.opened(document)
        if not document.sample:
            self._library_change("remember", document.path, document.format)
        if not self.restoring:
            self.active_id = document.id
        self.documentLoaded.emit(
            json.dumps(self.sessions[document.id].payload(), ensure_ascii=False)
        )
        self._finish_restore()
        self.remember_workspace()

    @Slot(str, str)
    def _failed(self, path, message):
        self.errorOccurred.emit(f"{Path(path).name}: {message}")
        self.publish_library()
        self._finish_restore()

    def sync_source(self, document_id, source=None):
        session = self.sessions.get(document_id)
        if session and source is not None:
            session.document.source = source.replace("\r\n", "\n").replace("\r", "\n")
        return session

    @Slot(str)
    def newDocument(self, document_format):
        if document_format not in FORMAT_EXTENSIONS or document_format == "PDF":
            return
        self.new_count += 1
        name = f"Untitled {self.new_count}{FORMAT_EXTENSIONS[document_format][0]}"
        doc = Document(
            id=f"untitled:{uuid4()}",
            name=name,
            path="",
            html="",
            headings=[],
            words=0,
            size=0,
            encoding="UTF-8",
            format=document_format,
        )
        session = EditSession.opened(doc)
        self.sessions[doc.id] = session
        self.documentLoaded.emit(json.dumps(session.payload()))

    @Slot(str, str, int)
    def previewDocument(self, document_id, source, revision):
        session = self.sync_source(document_id, source)
        if not session:
            return
        doc = session.document
        self.jobs.preview(
            document_id,
            PreviewRequest(
                doc.source, doc.format, Path(doc.path).parent if doc.path else None, revision
            ),
        )

    def _ask(self, title, text, buttons, default):
        box = QMessageBox(self.window)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default)
        return box.exec()

    def _confirm_changes(self, session):
        if not session.dirty:
            return True
        choice = self._ask(
            "Unsaved changes",
            f'Save changes to "{session.document.name}"?',
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self._save_session(session)
        return choice == QMessageBox.StandardButton.Discard

    @Slot(str, str, bool)
    def saveDocument(self, document_id, source, save_as):
        if self.window.manager.is_transferring(self.window, document_id):
            return
        session = self.sync_source(document_id, source)
        if session:
            self._save_session(session, save_as)

    def _save_session(self, session, save_as=False):
        doc = session.document
        target = Path(doc.path) if doc.path else None
        choose_path = save_as or target is None or doc.sample
        if choose_path:
            initial = str(
                target or Path(str(self.settings.value("lastFolder", Path.home()))) / doc.name
            )
            filters = file_filter(doc.format) + (
                ";;Text (*.txt)" if doc.format == "Markdown" else ""
            )
            name, selected_filter = QFileDialog.getSaveFileName(
                self.window,
                "Save As",
                initial,
                filters,
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not name:
                return False
            target = Path(name).expanduser()
            if not target.suffix:
                target = target.with_suffix(
                    ".txt"
                    if selected_filter.startswith("Text")
                    else FORMAT_EXTENSIONS[doc.format][0]
                )
            target = target.resolve()
            if any(
                str(target) in w.bridge.jobs.loads
                or (
                    not w.bridge.initialized
                    and target in [Path(p).expanduser().resolve() for p in w.bridge.initial_paths]
                )
                for w in self.window.manager.windows
            ):
                self.errorOccurred.emit(
                    "That file is still being opened. Please wait, then save again."
                )
                return False
            if any(
                s is not session and s.document.path == str(target)
                for w in self.window.manager.windows
                for s in w.bridge.sessions.values()
            ):
                self.errorOccurred.emit(
                    "That file is already open in another tab. Choose a different filename."
                )
                return False
        try:
            previous_path = doc.path if not doc.sample else None
            expected = fingerprint(target)
            same_file = str(target) == doc.path
            changed = same_file and expected != doc.fingerprint
            replacing = not same_file and expected is not None
            if changed or replacing:
                message = (
                    "The file has changed on disk since it was opened.\n\n"
                    if changed
                    else "A file already exists at this location.\n\n"
                )
                choice = self._ask(
                    "Replace file?",
                    message + f'Replace "{target.name}" with your current source?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    return False
            if session.dirty or choose_path or changed:
                session.save(target, expected)
            self.settings.setValue("lastFolder", str(target.parent))
            self._library_change("remember", doc.path, doc.format, previous_path)
            self.documentSaved.emit(json.dumps(session.payload(), ensure_ascii=False))
            self.remember_workspace()
            return True
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(
                f"Could not save {target.name}: {error}. Your edits are still open."
            )
            return False

    @Slot(str)
    @Slot(str, str)
    def reloadFile(self, document_id, source=None):
        if self.window.manager.is_transferring(self.window, document_id):
            return
        session = self.sync_source(document_id, source)
        if not session or not session.document.path or not self._confirm_changes(session):
            return
        try:
            doc = load_document(Path(session.document.path), sample=session.document.sample)
            doc.id = document_id
            self.sessions[document_id] = EditSession.opened(doc)
            self.jobs.discard(document_id)
            self.documentLoaded.emit(
                json.dumps(self.sessions[document_id].payload(), ensure_ascii=False)
            )
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Could not reload the file: {error}")

    @Slot(str)
    @Slot(str, str)
    def closeFile(self, document_id, source=None):
        if self.window.manager.is_transferring(self.window, document_id):
            return
        session = self.sync_source(document_id, source)
        if not session or not self._confirm_changes(session):
            return
        self.release_session(document_id)
        self.remember_workspace()

    def release_session(self, document_id):
        """Remove a closed or transferred buffer and stop its pending work."""
        self.sessions.pop(document_id, None)
        self.api_requests.cancel(document_id)
        self.jobs.discard(document_id)
        self.documentClosed.emit(document_id)

    @Slot(str)
    def confirmQuit(self, snapshots):
        try:
            if self.window.manager.has_transfer(self.window):
                self.errorOccurred.emit("Please wait for the tab to finish moving.")
                return
            values = json.loads(snapshots)
            if not isinstance(values, dict) or any(
                not isinstance(value, str) for value in values.values()
            ):
                raise ValueError("Invalid editor state")
            for document_id, source in values.items():
                self.sync_source(document_id, source)
            for session in list(self.sessions.values()):
                if not self._confirm_changes(session):
                    return
            self.remember_workspace()
            self.window.allow_close = True
            QTimer.singleShot(0, self.window.close)
        finally:
            self.window.close_pending = False

    @Slot()
    def openSample(self):
        self.load_paths([SAMPLE], sample=True)

    @Slot(str, str)
    def formatSource(self, document_id, source):
        session = self.sessions.get(document_id)
        if session:
            self.jobs.format_source(document_id, source, session.document.format)

    @Slot(str)
    def saveSettings(self, raw):
        try:
            cleaned = normalize_preferences(json.loads(raw))
        except (ValueError, TypeError):
            return
        self.settings.setValue("reading", json.dumps(cleaned))

    @Slot(str)
    def copyText(self, text):
        QApplication.clipboard().setText(text)

    @Slot(result=str)
    def chooseImage(self):
        name, _ = QFileDialog.getOpenFileName(
            self.window,
            "Insert image",
            str(self.settings.value("imageFolder", Path.home())),
            "Images (" + " ".join("*" + ext for ext in sorted(IMAGE_EXTENSIONS)) + ")",
        )
        if not name:
            return ""
        path = Path(name).resolve()
        self.settings.setValue("imageFolder", str(path.parent))
        return path.as_uri()

    @Slot(str, str, int, int)
    def requestPdfPage(self, document_id, source, number, revision):
        session = self.sessions.get(document_id)
        if not session or session.document.format != "PDF" or number < 0:
            return
        self.jobs.pdf_page(document_id, source, number, revision)

    @Slot(str, str, result=str)
    def validatePdfEdit(self, document_id, source):
        session = self.sessions.get(document_id)
        if not session or session.document.format != "PDF":
            return "Reopen the PDF and try again."
        try:
            from reader.pdf_documents import save_pdf

            if json.loads(source)["pdfId"] != json.loads(session.document.source)["pdfId"]:
                return "The PDF changed. Select the text again."
            save_pdf(source)
            return ""
        except (ValueError, RuntimeError, KeyError) as error:
            return str(error)

    @Slot()
    def toggleFullscreen(self):
        self.window.toggle_fullscreen()

    @Slot()
    def startWindowMove(self):
        # WebChannel messages are asynchronous. A quick release must not start
        # a move later or unexpectedly take the window out of fullscreen.
        if not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            return
        handle = self.window.windowHandle()
        if handle is None:
            return
        if self.window.isFullScreen():
            self.window.showNormal()
        # Let the compositor manage positioning, snapping and monitor scaling.
        # In particular, QWidget.move() cannot move top-level Wayland windows.
        if not handle.startSystemMove():
            self.errorOccurred.emit(
                "Could not start moving the window. Try dragging its system title bar."
            )

    @Slot()
    def minimize(self):
        self.window.showMinimized()

    @Slot(str, str, str)
    def detachDocument(self, document_id, source, view_state):
        self.window.manager.transfer(self.window, document_id, source, view_state)

    @Slot(str)
    def acceptTransfer(self, document_id):
        self.window.manager.finish_transfer(self.window, document_id)

    @Slot(str, str, str)
    def prepareTransfer(self, document_id, source, view_state):
        self.window.manager.prepare_transfer(self.window, document_id, source, view_state)

    @Slot(str, str, str)
    def startTabDrag(self, document_id, source, view_state):
        if (
            document_id not in self.sessions
            or not QApplication.mouseButtons() & Qt.MouseButton.LeftButton
        ):
            self.command.emit("tab-drag-finished")
            return
        manager = self.window.manager
        drag = QDrag(self.window.view)
        mime = QMimeData()
        mime.setData("application/x-khana-tab", document_id.encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.window.windowIcon().pixmap(32, 32))
        manager.dragging = (self.window, document_id, source, view_state)
        manager.drag_cancelled = False
        QApplication.instance().installEventFilter(manager)
        try:
            action = drag.exec(Qt.DropAction.MoveAction)
            if (
                action == Qt.DropAction.IgnoreAction
                and not manager.drag_cancelled
                and not self.window.frameGeometry().contains(QCursor.pos())
            ):
                manager.transfer(
                    self.window, document_id, source, view_state, position=QCursor.pos()
                )
        finally:
            QApplication.instance().removeEventFilter(manager)
            manager.dragging = None
            self.command.emit("tab-drag-finished")
            drag.deleteLater()

    @Slot()
    def quit(self):
        self.window.close()

    @Slot(str)
    def setDocumentTitle(self, title):
        self.window.setWindowTitle(f"{title} — {APP_NAME}" if title else APP_NAME)

    @Slot(str, str)
    def openLink(self, href, document_id):
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https", "mailto"}:
            QDesktopServices.openUrl(QUrl(href))
            return
        session = self.sessions.get(document_id)
        source = Path(session.document.path) if session and session.document.path else None
        if parsed.scheme or parsed.netloc or source is None:
            self.errorOccurred.emit("This type of link is not supported.")
            return
        target = (source.parent / unquote(parsed.path)).resolve()
        if target.suffix.lower() in EXTENSIONS and target.is_relative_to(source.parent):
            self.load_paths([target])
        else:
            self.errorOccurred.emit(
                "Only document links inside the current document folder can be opened."
            )
