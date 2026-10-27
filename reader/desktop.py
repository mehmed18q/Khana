"""Native desktop window and a small, explicit bridge to the local reading UI."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QSettings, QStandardPaths, QThreadPool, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox

from reader import APP_ID, APP_NAME, VERSION
from reader.documents import Document, EXTENSIONS, FORMAT_EXTENSIONS, IMAGE_EXTENSIONS, file_filter, load_document, render_source
from reader.editing import EditSession, fingerprint
from reader.library import ReadingLibrary
from reader.api_requests import ApiRequests

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reader" / "web"
SAMPLE = ROOT / "examples" / "welcome.md"


def default_settings_path() -> Path:
    # A one-file executable extracts resources to a temporary, read-only-in-
    # practice location. Preferences must survive removal of that directory.
    if getattr(sys, "frozen", False):
        return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)) / "settings.ini"
    return ROOT / ".local" / "settings.ini"


class LocalRequests(QWebEngineUrlRequestInterceptor):
    """No remote resources; document images are limited to explicitly opened folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folders: frozenset[Path] = frozenset()

    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() in {"qrc", "data"}:
            return
        if url.isLocalFile():
            path = Path(url.toLocalFile()).resolve()
            if path.is_relative_to(WEB):
                return
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                return
        info.block(True)


class ReaderPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.isLocalFile() and Path(url.toLocalFile()).resolve() == WEB / "index.html":
            return True
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme() in {"https", "http", "mailto"}:
                QDesktopServices.openUrl(url)
        return False


class LoadSignals(QObject):
    finished = Signal(str, str)
    failed = Signal(str, str)


class LoadTask(QRunnable):
    def __init__(self, path: Path, sample=False):
        super().__init__()
        self.path = path
        self.sample = sample
        self.signals = LoadSignals()

    def run(self):
        try:
            document = load_document(self.path, sample=self.sample)
            self.signals.finished.emit(str(self.path), json.dumps(document.to_dict(), ensure_ascii=False))
        except (OSError, ValueError) as error:
            if isinstance(error, FileNotFoundError):
                message = "File not found. It may have been moved or deleted."
            elif isinstance(error, PermissionError):
                message = "You do not have permission to read this file."
            else:
                message = str(error)
            self.signals.failed.emit(str(self.path), message)
        except Exception:
            self.signals.failed.emit(str(self.path), "This file could not be read.")


class PdfPageTask(QRunnable):
    def __init__(self, document_id, source, number, revision):
        super().__init__()
        self.document_id, self.source, self.number, self.revision = document_id, source, number, revision
        self.signals = LoadSignals()

    def run(self):
        from reader.pdf_documents import page_image
        payload = {'id': self.document_id, 'number': self.number, 'revision': self.revision}
        try:
            payload['url'] = page_image(self.source, self.number)
        except Exception as error:
            payload['error'] = str(error)
        self.signals.finished.emit(self.document_id, json.dumps(payload))


class PreviewTask(QRunnable):
    def __init__(self, document_id, source, document_format, folder, revision):
        super().__init__()
        self.document_id, self.source = document_id, source
        self.document_format, self.folder, self.revision = document_format, folder, revision
        self.signals = LoadSignals()

    def run(self):
        try:
            rendered = render_source(self.source, self.document_format, self.folder)
            self.signals.finished.emit(self.document_id, json.dumps({"id": self.document_id, "revision": self.revision, **rendered}, ensure_ascii=False))
        except Exception as error:
            self.signals.failed.emit(self.document_id, str(error))


class FormatSourceTask(QRunnable):
    def __init__(self, document_id, source, document_format):
        super().__init__()
        self.document_id, self.source, self.document_format = document_id, source, document_format
        self.signals = LoadSignals()

    def run(self):
        result = {'id': self.document_id}
        try:
            from reader.source_formatting import beautify_source
            result['source'] = beautify_source(self.source, self.document_format)
        except Exception as error:
            result['error'] = f'Could not format {self.document_format}: {str(error)[:500]}'
        self.signals.finished.emit(self.document_id, json.dumps(result, ensure_ascii=False))


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
        self.settings = QSettings(str(settings_path or default_settings_path()), QSettings.Format.IniFormat)
        self.library_error = None
        try:
            self.library = ReadingLibrary(Path(self.settings.fileName()).with_name('library.sqlite3'))
        except (OSError, sqlite3.Error) as error:
            self.library = None
            self.library_error = str(error)
        self.active_id = None
        self.restoring = False
        self.restore_active = None
        self.opened: set[Path] = set()
        self.sessions: dict[str, EditSession] = {}
        self.preview_tasks: dict[str, PreviewTask] = {}
        self.format_tasks: dict[str, FormatSourceTask] = {}
        self.pdf_tasks: dict[tuple, PdfPageTask] = {}
        self.pending_previews: dict[str, tuple] = {}
        self.new_count = 0
        self.tasks: dict[str, LoadTask] = {}
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.initialized = False
        self.api_requests = ApiRequests(self)
        self.api_requests.finished.connect(self.apiResponse)

    @Slot(str, str, str)
    def executeApiRequest(self, document_id, request_id, raw):
        session = self.sessions.get(document_id)
        if not session or document_id != self.active_id or session.document.format not in {'JSON', 'YAML'}:
            self.api_requests.fail(document_id, request_id, 'Open the API document before sending a request.')
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
        self.settingsLoaded.emit(str(self.settings.value("reading", "{}")))
        entries = self._emit_library()
        if self.library_error:
            self.errorOccurred.emit(f'Reading library unavailable: {self.library_error}')
        workspace = {'paths': [], 'active': None}
        if self.library:
            try:
                workspace = self.library.workspace()
            except (sqlite3.Error, ValueError) as error:
                self.errorOccurred.emit(f'Could not restore the reading session: {error}')
        paths = [Path(path) for path in workspace['paths'] if Path(path).is_file()]
        paths += [Path(path).resolve() for path in self.initial_paths if Path(path).resolve() not in paths]
        self.restore_active = str(Path(self.initial_paths[-1]).resolve()) if self.initial_paths else workspace['active']
        if paths:
            self.restoring = True
            self.load_paths(paths)
        elif entries == []:
            self.load_paths([SAMPLE], sample=True)
        else:
            self.command.emit('empty')

    def _emit_library(self):
        try:
            entries = self.library.entries() if self.library else []
            for entry in entries:
                entry['missing'] = not Path(entry['path']).is_file()
            self.libraryChanged.emit(json.dumps({'available': self.library is not None, 'entries': entries}, ensure_ascii=False))
            return entries
        except (sqlite3.Error, ValueError) as error:
            self.errorOccurred.emit(f'Could not read the document library: {error}')

    def _library_change(self, method, *args):
        if not self.library:
            return False
        try:
            getattr(self.library, method)(*args)
            self._emit_library()
            return True
        except (sqlite3.Error, OSError, ValueError) as error:
            self.errorOccurred.emit(f'Could not save reading information: {error}')
            return False

    def _remember_session(self):
        if self.restoring or not self.library:
            return
        paths = [s.document.path for s in self.sessions.values() if s.document.path and not s.document.sample]
        active = self.sessions.get(self.active_id)
        active_path = active.document.path if active and active.document.path in paths else None
        try:
            self.library.save_workspace(paths, active_path)
        except (sqlite3.Error, OSError) as error:
            self.errorOccurred.emit(f'Could not remember the open documents: {error}')

    def _finish_restore(self):
        if self.restoring and not self.tasks:
            self.restoring = False
            self.active_id = next((s.document.id for s in self.sessions.values() if s.document.path == self.restore_active),
                                  next(reversed(self.sessions), None))
            if self.active_id:
                self.documentActivated.emit(self.active_id)
            else:
                self.command.emit('empty')
            self._remember_session()

    @Slot(str)
    def activateDocument(self, document_id):
        if document_id in self.sessions and not self.restoring:
            self.active_id = document_id
            self._remember_session()

    @Slot(str)
    def openLibrary(self, path):
        if not self.library:
            return
        try:
            if not self.library.get(path):
                return
        except (sqlite3.Error, ValueError) as error:
            self.errorOccurred.emit(f'Could not read the document library: {error}')
            return
        existing = next((s.document.id for s in self.sessions.values() if s.document.path == path), None)
        self.load_paths([Path(path)])
        if existing:
            self.command.emit('resume-annotation')

    @Slot(str, bool)
    def starDocument(self, path, starred):
        self._library_change('set_starred', path, starred)

    @Slot(str)
    def forgetDocument(self, path):
        if any(s.document.path == path for s in self.sessions.values()) or path in self.tasks:
            self.errorOccurred.emit('Close the document before removing it from the library.')
            return
        if self._library_change('forget', path):
            self._remember_session()

    @Slot(str, str, str, result=bool)
    def saveAnnotation(self, document_id, source, raw):
        session = self._sync(document_id, source)
        if not session or not session.document.path or session.document.sample:
            self.errorOccurred.emit('Save this document before adding marks or notes.')
            return False
        try:
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise ValueError('Invalid annotation.')
            if not item.get('id') and session.dirty:
                raise ValueError('Save your document changes before adding a mark or note.')
            anchor = item.get('anchor')
            if isinstance(anchor, dict) and not item.get('id'):
                anchor['fingerprint'] = session.document.fingerprint
            return self._library_change('save_annotation', session.document.path, item.get('id'),
                                        item.get('kind'), item.get('label'), item.get('body', ''), anchor)
        except (ValueError, TypeError) as error:
            self.errorOccurred.emit(str(error))
            return False

    @Slot(str, str)
    def deleteAnnotation(self, path, identifier):
        self._library_change('delete_annotation', path, identifier)

    @Slot(str, str)
    def resumeAnnotation(self, path, identifier):
        self._library_change('resume', path, identifier)

    @Slot()
    def openFiles(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self.window, "Open a document", str(self.settings.value("lastFolder", Path.home())),
            'Documents (' + ' '.join('*' + ext for ext in sorted(EXTENSIONS | {ext.upper() for ext in EXTENSIONS})) + ');;'
            + ';;'.join(file_filter(name) for name in FORMAT_EXTENSIONS) + ';;All files (*)',
        )
        if paths:
            self.settings.setValue("lastFolder", str(Path(paths[0]).parent))
            self.load_paths([Path(p) for p in paths])

    def load_paths(self, paths, sample=False):
        for path in paths:
            path = path.expanduser().resolve()
            key = str(path)
            existing = next((s.document.id for s in self.sessions.values() if s.document.path == key), None)
            if existing:
                self.active_id = existing
                self.documentActivated.emit(existing)
                self._remember_session()
                continue
            if key in self.tasks:
                continue
            task = LoadTask(path, sample)
            task.signals.finished.connect(self._loaded)
            task.signals.failed.connect(self._failed)
            self.tasks[key] = task
            self.pool.start(task)
        self.busyChanged.emit(bool(self.tasks))

    @Slot(str, str)
    def _loaded(self, path, payload):
        self.tasks.pop(path, None)
        document = Document(**json.loads(payload))
        if document.id in self.sessions or document.id in self.preview_tasks:
            document.id = f"{uuid4()}:{path}"
        self.sessions[document.id] = EditSession.opened(document)
        if not document.sample:
            self._library_change('remember', document.path, document.format)
        if not self.restoring:
            self.active_id = document.id
        self._refresh_folders()
        self.documentLoaded.emit(json.dumps(self.sessions[document.id].payload(), ensure_ascii=False))
        self._finish_restore()
        self._remember_session()
        self.busyChanged.emit(bool(self.tasks))

    @Slot(str, str)
    def _failed(self, path, message):
        self.tasks.pop(path, None)
        self.errorOccurred.emit(f"{Path(path).name}: {message}")
        self._emit_library()
        self._finish_restore()
        self.busyChanged.emit(bool(self.tasks))

    def _refresh_folders(self):
        self.opened = {Path(s.document.path) for s in self.sessions.values() if s.document.path}
        self.window.requests.folders = frozenset(path.parent for path in self.opened)

    def _sync(self, document_id, source=None):
        session = self.sessions.get(document_id)
        if session and source is not None:
            session.document.source = source.replace("\r\n", "\n").replace("\r", "\n")
        return session

    @Slot(str)
    def newDocument(self, document_format):
        if document_format not in FORMAT_EXTENSIONS or document_format == 'PDF':
            return
        self.new_count += 1
        name = f"Untitled {self.new_count}{FORMAT_EXTENSIONS[document_format][0]}"
        doc = Document(id=f"untitled:{uuid4()}", name=name, path="", html="", headings=[],
                       words=0, size=0, encoding="UTF-8", format=document_format)
        session = EditSession.opened(doc)
        self.sessions[doc.id] = session
        self.documentLoaded.emit(json.dumps(session.payload()))

    @Slot(str, str, int)
    def previewDocument(self, document_id, source, revision):
        session = self._sync(document_id, source)
        if not session:
            return
        doc = session.document
        self.pending_previews[document_id] = (doc.source, doc.format, Path(doc.path).parent if doc.path else None, revision)
        self._start_preview(document_id)

    def _start_preview(self, document_id):
        if document_id in self.preview_tasks or document_id not in self.pending_previews:
            return
        source, document_format, folder, revision = self.pending_previews.pop(document_id)
        task = PreviewTask(document_id, source, document_format, folder, revision)
        self.preview_tasks[document_id] = task
        task.signals.finished.connect(self._preview_finished)
        task.signals.failed.connect(self._preview_failed)
        self.pool.start(task)

    @Slot(str, str)
    def _preview_finished(self, document_id, payload):
        self.preview_tasks.pop(document_id, None)
        if document_id in self.sessions:
            self.previewReady.emit(payload)
            self._start_preview(document_id)

    @Slot(str, str)
    def _preview_failed(self, document_id, message):
        task = self.preview_tasks.pop(document_id, None)
        if document_id in self.sessions and task:
            self.previewFailed.emit(document_id, task.revision, message)
            self._start_preview(document_id)

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
        choice = self._ask("Unsaved changes", f'Save changes to "{session.document.name}"?',
                           QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                           QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Save:
            return self._save_session(session)
        return choice == QMessageBox.StandardButton.Discard

    @Slot(str, str, bool)
    def saveDocument(self, document_id, source, save_as):
        session = self._sync(document_id, source)
        if session:
            self._save_session(session, save_as)

    def _save_session(self, session, save_as=False):
        doc = session.document
        target = Path(doc.path) if doc.path else None
        choose_path = save_as or target is None or doc.sample
        if choose_path:
            initial = str(target or Path(str(self.settings.value("lastFolder", Path.home()))) / doc.name)
            filters = file_filter(doc.format) + (';;Text (*.txt)' if doc.format == 'Markdown' else '')
            name, selected_filter = QFileDialog.getSaveFileName(
                self.window, "Save As", initial, filters, options=QFileDialog.Option.DontConfirmOverwrite)
            if not name:
                return False
            target = Path(name).expanduser()
            if not target.suffix:
                target = target.with_suffix('.txt' if selected_filter.startswith('Text') else FORMAT_EXTENSIONS[doc.format][0])
            target = target.resolve()
            if str(target) in self.tasks:
                self.errorOccurred.emit("That file is still being opened. Please wait, then save again.")
                return False
            if any(s is not session and s.document.path == str(target) for s in self.sessions.values()):
                self.errorOccurred.emit("That file is already open in another tab. Choose a different filename.")
                return False
        try:
            previous_path = doc.path if not doc.sample else None
            expected = fingerprint(target)
            same_file = str(target) == doc.path
            changed = same_file and expected != doc.fingerprint
            replacing = not same_file and expected is not None
            if changed or replacing:
                message = ("The file has changed on disk since it was opened.\n\n" if changed else "A file already exists at this location.\n\n")
                choice = self._ask("Replace file?", message + f'Replace "{target.name}" with your current source?',
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
                if choice != QMessageBox.StandardButton.Yes:
                    return False
            if session.dirty or choose_path or changed:
                session.save(target, expected)
            self.settings.setValue("lastFolder", str(target.parent))
            self._refresh_folders()
            self._library_change('remember', doc.path, doc.format, previous_path)
            self.documentSaved.emit(json.dumps(session.payload(), ensure_ascii=False))
            self._remember_session()
            return True
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Could not save {target.name}: {error}. Your edits are still open.")
            return False

    @Slot(str)
    @Slot(str, str)
    def reloadFile(self, document_id, source=None):
        session = self._sync(document_id, source)
        if not session or not session.document.path or not self._confirm_changes(session):
            return
        try:
            doc = load_document(Path(session.document.path), sample=session.document.sample)
            doc.id = document_id
            self.sessions[document_id] = EditSession.opened(doc)
            self.pending_previews.pop(document_id, None)
            self.documentLoaded.emit(json.dumps(self.sessions[document_id].payload(), ensure_ascii=False))
        except (OSError, ValueError) as error:
            self.errorOccurred.emit(f"Could not reload the file: {error}")

    @Slot(str)
    @Slot(str, str)
    def closeFile(self, document_id, source=None):
        session = self._sync(document_id, source)
        if not session or not self._confirm_changes(session):
            return
        del self.sessions[document_id]
        self.api_requests.cancel(document_id)
        self.pending_previews.pop(document_id, None)
        self._refresh_folders()
        self.documentClosed.emit(document_id)
        self._remember_session()

    @Slot(str)
    def confirmQuit(self, snapshots):
        try:
            values = json.loads(snapshots)
            if not isinstance(values, dict) or any(not isinstance(value, str) for value in values.values()):
                raise ValueError("Invalid editor state")
            for document_id, source in values.items():
                self._sync(document_id, source)
            for session in list(self.sessions.values()):
                if not self._confirm_changes(session):
                    return
            self._remember_session()
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
        if not session or document_id in self.format_tasks:
            return
        task = FormatSourceTask(document_id, source, session.document.format)
        task.signals.finished.connect(self._source_formatted)
        self.format_tasks[document_id] = task
        self.pool.start(task)

    @Slot(str, str)
    def _source_formatted(self, document_id, result):
        self.format_tasks.pop(document_id, None)
        self.sourceFormatted.emit(result)

    @Slot(str)
    def saveSettings(self, raw):
        try:
            values = json.loads(raw)
            if not isinstance(values, dict):
                return
            cleaned = {
                "theme": values.get("theme") if values.get("theme") in {"light", "dark"} else "light",
                "direction": values.get("direction") if values.get("direction") in {"smart", "rtl", "ltr"} else "smart",
                "fontSize": max(14, min(24, int(values.get("fontSize", 17)))),
                "lineHeight": max(1.6, min(2.6, float(values.get("lineHeight", 2)))),
                "wide": bool(values.get("wide", False)),
                "syncScroll": bool(values.get("syncScroll", True)),
                "previewZoom": max(50, min(300, int(values.get("previewZoom", 100)))),
            }
        except (ValueError, TypeError):
            return
        self.settings.setValue("reading", json.dumps(cleaned))

    @Slot(str)
    def copyText(self, text):
        QApplication.clipboard().setText(text)

    @Slot(result=str)
    def chooseImage(self):
        name, _ = QFileDialog.getOpenFileName(self.window, 'Insert image', str(self.settings.value('imageFolder', Path.home())),
                                             'Images (' + ' '.join('*' + ext for ext in sorted(IMAGE_EXTENSIONS)) + ')')
        if not name:
            return ''
        path = Path(name).resolve()
        self.settings.setValue('imageFolder', str(path.parent))
        return path.as_uri()

    @Slot(str, str, int, int)
    def requestPdfPage(self, document_id, source, number, revision):
        session = self.sessions.get(document_id)
        if not session or session.document.format != 'PDF' or number < 0:
            return
        task = PdfPageTask(document_id, source, number, revision)
        key = (document_id, number, revision)
        if key in self.pdf_tasks:
            return
        self.pdf_tasks[key] = task
        task.signals.finished.connect(self._pdf_finished)
        self.pool.start(task)

    @Slot(str, str)
    def _pdf_finished(self, document_id, payload):
        result = json.loads(payload)
        self.pdf_tasks.pop((document_id, result['number'], result['revision']), None)
        if document_id in self.sessions:
            self.pdfPageReady.emit(payload)

    @Slot(str, str, result=str)
    def validatePdfEdit(self, document_id, source):
        session = self.sessions.get(document_id)
        if not session or session.document.format != 'PDF':
            return 'Reopen the PDF and try again.'
        try:
            from reader.pdf_documents import save_pdf
            if json.loads(source)['pdfId'] != json.loads(session.document.source)['pdfId']:
                return 'The PDF changed. Select the text again.'
            save_pdf(source)
            return ''
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
            self.errorOccurred.emit('Could not start moving the window. Try dragging its system title bar.')

    @Slot()
    def minimize(self):
        self.window.showMinimized()

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
            self.errorOccurred.emit("Only document links inside the current document folder can be opened.")


class ReaderView(QWebEngineView):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.page().runJavaScript("document.body.classList.add('dropping')")
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.page().runJavaScript("document.body.classList.remove('dropping')")
        event.accept()

    def dropEvent(self, event):
        self.page().runJavaScript("document.body.classList.remove('dropping')")
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.window.bridge.load_paths(paths)
            event.acceptProposedAction()


class ReaderWindow(QMainWindow):
    def __init__(self, initial_paths=(), settings_path=None):
        super().__init__()
        self.allow_close = False
        self.close_pending = False
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(WEB / "icon.svg")))
        self.resize(1320, 900)
        self.setMinimumSize(860, 600)
        self.view = ReaderView(self)
        self.profile = QWebEngineProfile(self)
        self.requests = LocalRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.requests)
        self.page = ReaderPage(self.profile, self.view)
        self.view.setPage(self.page)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        self.setCentralWidget(self.view)
        self.bridge = Bridge(self, initial_paths, settings_path)
        geometry = self.bridge.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("native", self.bridge)
        self.page.setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(str(WEB / "index.html")))

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        if self.bridge.initialized and not self.allow_close:
            event.ignore()
            if not self.close_pending:
                self.close_pending = True
                self.bridge.command.emit("quit-request")
            return
        self.bridge.settings.setValue("geometry", self.saveGeometry())
        self.bridge.settings.sync()
        self.bridge.api_requests.cancel()
        self.bridge.pool.waitForDone()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description="Khana — Local Markdown and HTML reader for Persian and English")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument("files", nargs="*", type=Path, help="Markdown or HTML files to open")
    args = parser.parse_args()
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)
    QApplication.setApplicationVersion(VERSION)
    app = QApplication(sys.argv[:1])
    app.setApplicationDisplayName(APP_NAME)
    # Wayland app_id must match the installed .desktop basename. The desktop
    # shell reads the human-readable Name and themed Icon from that entry.
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(WEB / "icon.svg")))
    window = ReaderWindow(args.files)
    window.showFullScreen()
    return app.exec()
