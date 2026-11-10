"""Explicit WebChannel commands coordinating document sessions and native UI."""

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QFile,
    QMimeData,
    QObject,
    QSettings,
    Qt,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QCursor, QDesktopServices, QDrag, QPalette
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

from reader import APP_NAME, VERSION
from reader.api_requests import ApiRequests
from reader.documents import (
    EXTENSIONS,
    FORMAT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    Document,
    file_filter,
    format_for_path,
    load_document,
)
from reader.editing import EditSession, fingerprint
from reader.library import ReadingLibrary
from reader.preferences import normalize_preferences
from reader.resources import SAMPLE
from reader.ui.jobs import DocumentJobs, PreviewRequest
from reader.ui.settings import default_settings_path
from reader.ui.spelling import SpellingJobs


class Bridge(QObject):
    documentLoaded = Signal(str)
    documentSaved = Signal(str)
    documentClosed = Signal(str)
    documentActivated = Signal(str)
    documentRenamed = Signal(str, str, str)
    previewReady = Signal(str)
    previewFailed = Signal(str, int, str)
    errorOccurred = Signal(str)
    busyChanged = Signal(bool)
    settingsLoaded = Signal(str)
    systemThemeChanged = Signal(str)
    themePreferencesChanged = Signal(str)
    focusModeChanged = Signal(bool)
    libraryChanged = Signal(str)
    pdfPageReady = Signal(str)
    sourceFormatted = Signal(str)
    apiResponse = Signal(str)
    command = Signal(str)
    spellingReady = Signal(str)
    spellingChanged = Signal()
    interfacePreferencesChanged = Signal(str)

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
        self.spelling = SpellingJobs(self)
        self.spelling.ready.connect(self.spellingReady)
        self.draft_spelling = {}
        self.api_requests.finished.connect(self.apiResponse)
        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.styleHints().colorSchemeChanged.connect(self.publish_system_theme)
            application.paletteChanged.connect(self.publish_system_theme)

    def publish_system_theme(self, *_):
        application = QApplication.instance()
        if not isinstance(application, QApplication):
            return
        scheme = application.styleHints().colorScheme()
        dark = scheme == Qt.ColorScheme.Dark
        if scheme == Qt.ColorScheme.Unknown:
            dark = application.palette().color(QPalette.ColorRole.Window).lightness() < 128
        self.systemThemeChanged.emit("dark" if dark else "light")

    @Property(str, constant=True)
    def appVersion(self):
        return VERSION

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
        self.publish_system_theme()
        preferences = normalize_preferences(preferences)
        self.window.setProperty("language", preferences["language"])
        if isinstance(self.window, QWidget):
            self.window.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft
                if preferences["language"] in {"fa", "ar"}
                else Qt.LayoutDirection.LeftToRight
            )
        self.settingsLoaded.emit(json.dumps(preferences))
        self.focusModeChanged.emit(self.window.focus_mode)
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
                    {
                        "available": self.library is not None,
                        "entries": entries,
                        "categories": self.library.categories() if self.library else [],
                    },
                    ensure_ascii=False,
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

    @Slot(str, str)
    def openLibraryInLayout(self, path, layout):
        if layout not in {"columns", "rows", "grid"} or not self._known_file(path):
            return
        owner = self.window.manager.path_owner(path) or self.window
        owner.bridge.command.emit("layout-mode:" + layout)
        owner.bridge.load_paths([Path(path)])
        self.window.manager.reveal(owner)

    @Slot(str, bool)
    def pinDocument(self, path, pinned):
        self._library_change("set_pinned", path, pinned)

    @Slot(str, str, bool)
    def moveDocument(self, path, neighbor, before):
        self._library_change("move_relative", path, neighbor, before)

    @staticmethod
    def _paths(raw):
        paths = json.loads(raw)
        if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError("Choose saved files first.")
        return list(dict.fromkeys(paths))

    def _library_command(self, operation):
        if not self.library:
            return "The document library is unavailable."
        try:
            operation()
            for window in self.window.manager.windows:
                window.bridge.publish_library()
            return ""
        except (sqlite3.Error, OSError, ValueError) as error:
            return str(error)

    @Slot(str, str, result=str)
    def createCategory(self, name, paths):
        return self._library_command(lambda: self.library.create_category(name, self._paths(paths)))

    @Slot(str, str, result=str)
    def renameCategory(self, identifier, name):
        return self._library_command(lambda: self.library.rename_category(identifier, name))

    @Slot(str, result=str)
    def deleteCategory(self, identifier):
        return self._library_command(lambda: self.library.delete_category(identifier))

    @Slot(str, str, bool, result=str)
    def moveCategory(self, identifier, neighbor, before):
        return self._library_command(
            lambda: self.library.move_category(identifier, neighbor, before)
        )

    @Slot(str, str, bool, result=str)
    def collapseCategory(self, identifier, scope, collapsed):
        return self._library_command(
            lambda: self.library.collapse_category(identifier, scope, collapsed)
        )

    @Slot(str, str, result=str)
    def assignDocumentCategories(self, paths, identifier):
        return self._library_command(
            lambda: self.library.assign_category(self._paths(paths), identifier)
        )

    @Slot(str, str, bool, result=str)
    def setDocumentFlags(self, paths, flag, value):
        return self._library_command(
            lambda: self.library.set_files_flag(self._paths(paths), flag, value)
        )

    @Slot(str, str, result=str)
    def renameFile(self, path, name):
        if not self.library:
            return "The document library is unavailable."
        old = self._known_file(path)
        if not old or not old.is_file():
            return "The file is no longer available."
        name = name.strip()
        if not name or name in {".", ".."} or any(c in name for c in "/\\\x00\n\r"):
            return "Enter a file name without folder separators."
        target = old.with_name(name)
        if target == old:
            return ""
        if target.exists() or target.is_symlink():
            return "A file with that name already exists."
        try:
            if format_for_path(target) != format_for_path(old):
                return "Keep an extension for the same document format."
        except ValueError as error:
            return str(error)
        manager = self.window.manager
        if manager.path_owner(str(target)):
            return "The destination is already open in another tab."
        for window in manager.windows:
            if (
                path in window.bridge.jobs.loads
                or (
                    not window.bridge.initialized
                    and old in [Path(p).expanduser().resolve() for p in window.bridge.initial_paths]
                )
                or any(
                    s.document.path == path and manager.is_transferring(window, s.document.id)
                    for s in window.bridge.sessions.values()
                )
            ):
                return "Wait for this file to finish opening or moving."
        renamed = False

        def rename():
            nonlocal renamed
            file = QFile(str(old))
            if not file.rename(str(target)):
                raise OSError(file.errorString())
            renamed = True

        try:
            self.library.rename_document(path, str(target), rename)
        except (OSError, sqlite3.Error, ValueError) as error:
            if renamed and not QFile.rename(str(target), str(old)):
                return f"The file is now at {target}, but library update failed: {error}"
            return str(error)
        for window in manager.windows:
            for session in window.bridge.sessions.values():
                if session.document.path == path:
                    session.document.path = str(target)
                    session.document.name = target.name
            window.bridge.documentRenamed.emit(path, str(target), target.name)
            window.bridge.publish_library()
        self.remember_workspace()
        return ""

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
        persian = self.window.property("language") == "fa"
        arabic = self.window.property("language") == "ar"
        if persian:
            title = {"Unsaved changes": "تغییرات ذخیره‌نشده", "Replace file?": "جایگزینی فایل؟"}.get(
                title, title
            )
            if text.startswith('Save changes to "'):
                text = "تغییرات «" + text[17:-2] + "» ذخیره شود؟"
            else:
                text = text.replace(
                    "The file has changed on disk since it was opened.",
                    "فایل از زمان باز شدن روی دیسک تغییر کرده است.",
                ).replace("A file already exists at this location.", "فایلی در این مسیر وجود دارد.")
                if 'Replace "' in text:
                    prefix, name = text.split('Replace "', 1)
                    text = prefix + "فایل «" + name.split('"', 1)[0] + "» با متن فعلی جایگزین شود؟"
        elif arabic:
            title = {
                "Unsaved changes": "تغييرات غير محفوظة",
                "Replace file?": "استبدال الملف؟",
            }.get(title, title)
            if text.startswith('Save changes to "'):
                text = "هل تريد حفظ التغييرات في «" + text[17:-2] + "»؟"
            else:
                text = text.replace(
                    "The file has changed on disk since it was opened.",
                    "تغيّر الملف على القرص منذ فتحه.",
                ).replace(
                    "A file already exists at this location.", "يوجد ملف في هذا الموقع بالفعل."
                )
                if 'Replace "' in text:
                    prefix, name = text.split('Replace "', 1)
                    text = prefix + "هل تريد استبدال «" + name.split('"', 1)[0] + "» بالنص الحالي؟"
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default)
        if persian or arabic:
            for flag, farsi, arabic_label in (
                (QMessageBox.StandardButton.Save, "ذخیره", "حفظ"),
                (QMessageBox.StandardButton.Discard, "ذخیره نشود", "تجاهل"),
                (QMessageBox.StandardButton.Cancel, "انصراف", "إلغاء"),
                (QMessageBox.StandardButton.Yes, "بله", "نعم"),
            ):
                if box.button(flag):
                    box.button(flag).setText(farsi if persian else arabic_label)
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
            spelling_key = self._spelling_key(doc.id)
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
            new_spelling_key = self._spelling_key(doc.id)
            ignored = self.draft_spelling.pop(doc.id, set())
            if spelling_key and spelling_key != new_spelling_key:
                ignored.update(self.settings.value(spelling_key, [], type=list))
            if ignored and new_spelling_key:
                ignored.update(self.settings.value(new_spelling_key, [], type=list))
                self.settings.setValue(new_spelling_key, sorted(ignored))
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

    @Slot(str, result=bool)
    def closeFiles(self, raw):
        try:
            values = json.loads(raw)
            if not isinstance(values, dict) or any(not isinstance(s, str) for s in values.values()):
                return False
            if any(
                self.window.manager.is_transferring(self.window, identifier)
                for identifier in values
            ):
                return False
            sessions = [
                self.sync_source(identifier, source) for identifier, source in values.items()
            ]
            if not all(self._confirm_changes(s) for s in sessions if s):
                return False
            for identifier in values:
                if identifier in self.sessions:
                    self.release_session(identifier)
            self.remember_workspace()
            return True
        except ValueError:
            return False

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
        self.window.setProperty("language", cleaned["language"])
        if isinstance(self.window, QWidget):
            self.window.setLayoutDirection(
                Qt.LayoutDirection.RightToLeft
                if cleaned["language"] in {"fa", "ar"}
                else Qt.LayoutDirection.LeftToRight
            )
        appearance = json.dumps({key: cleaned[key] for key in ("theme", "palette")})
        interface = json.dumps({key: cleaned[key] for key in ("language", "spellcheck")})
        for window in self.window.manager.windows:
            if window is not self.window:
                window.bridge.themePreferencesChanged.emit(appearance)
                window.setProperty("language", cleaned["language"])
                if isinstance(window, QWidget):
                    window.setLayoutDirection(self.window.layoutDirection())
                window.bridge.interfacePreferencesChanged.emit(interface)

    @Slot(str)
    def copyText(self, text):
        QApplication.clipboard().setText(text)

    @Slot(result=str)
    def clipboardText(self):
        return QApplication.clipboard().text()

    def _spelling_key(self, document_id):
        session = self.sessions.get(document_id)
        path = session.document.path if session else None
        return "spelling/documents/" + sha256(str(path).encode()).hexdigest() if path else None

    def _ignored_spelling(self, document_id):
        key = self._spelling_key(document_id)
        words = self.settings.value("spelling/global", [], type=list)
        words += self.settings.value(key, [], type=list) if key else []
        return words + list(self.draft_spelling.get(document_id, set()))

    @Slot(str, int, str)
    def checkSpelling(self, document_id, token, raw):
        if document_id not in self.sessions:
            return
        try:
            words = json.loads(raw)
            if not isinstance(words, list) or len(words) > 20000:
                return
            words = list(
                dict.fromkeys(
                    word for word in words if isinstance(word, str) and 1 < len(word) <= 80
                )
            )
        except (ValueError, TypeError):
            return
        self.spelling.submit(
            {
                "id": document_id,
                "token": token,
                "kind": "check",
                "words": words,
                "ignored": self._ignored_spelling(document_id),
            }
        )

    @Slot(str, int, str)
    def spellingSuggestions(self, document_id, token, word):
        if document_id in self.sessions and 1 < len(word) <= 80:
            self.spelling.submit(
                {"id": document_id, "token": token, "kind": "suggest", "word": word}
            )

    @Slot(str, str, bool)
    def ignoreSpelling(self, document_id, word, everywhere):
        if document_id not in self.sessions or not 1 < len(word) <= 80:
            return
        key = "spelling/global" if everywhere else self._spelling_key(document_id)
        word = word.casefold()
        if key:
            values = set(self.settings.value(key, [], type=list))
            values.add(word)
            self.settings.setValue(key, sorted(values))
            self.settings.sync()
        else:
            self.draft_spelling.setdefault(document_id, set()).add(word)
        for window in self.window.manager.windows:
            window.bridge.spellingChanged.emit()

    def _known_file(self, path):
        if not path:
            return None
        if any(s.document.path == path for s in self.sessions.values()):
            return Path(path)
        try:
            if self.library and self.library.get(path):
                return Path(path)
        except (sqlite3.Error, ValueError) as error:
            self.errorOccurred.emit(f"Could not read the document library: {error}")
        return None

    @Slot(str, bool, result=bool)
    def copyFile(self, path, cut):
        return self.copyFiles(json.dumps([path]), cut)

    @Slot(str, bool, result=bool)
    def copyFiles(self, raw, cut):
        try:
            paths = self._paths(raw)
        except ValueError:
            return False
        files = [self._known_file(path) for path in paths]
        if not files or any(not file or not file.is_file() for file in files):
            self.errorOccurred.emit("The file is no longer available. Save it before copying.")
            return False
        urls = [QUrl.fromLocalFile(str(file)) for file in files]
        mime = QMimeData()
        mime.setUrls(urls)
        # File managers consume these formats in addition to text/uri-list.
        operation = "cut" if cut else "copy"
        mime.setData(
            "x-special/gnome-copied-files",
            (
                operation
                + "\n"
                + "\n".join(
                    url.toString(QUrl.ComponentFormattingOption.FullyEncoded) for url in urls
                )
            ).encode(),
        )
        mime.setData("application/x-kde-cutselection", b"1" if cut else b"0")
        mime.setData(
            'application/x-qt-windows-mime;value="Preferred DropEffect"',
            (2 if cut else 1).to_bytes(4, "little"),
        )
        QApplication.clipboard().setMimeData(mime)
        return True

    @Slot(str)
    def openFileFolder(self, path):
        file = self._known_file(path)
        if not file or not file.parent.is_dir():
            self.errorOccurred.emit("The containing folder is no longer available.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(file.parent))):
            self.errorOccurred.emit("Could not open the containing folder.")

    @Slot(str, str)
    def openDocumentFolder(self, document_id, path):
        session = self.sessions.get(document_id)
        if not session or not session.document.path:
            return
        # Only ancestors of this open document can be opened from its breadcrumb.
        folder = Path(path)
        if folder not in Path(session.document.path).parents:
            return
        if not folder.is_dir():
            self.errorOccurred.emit("The folder is no longer available.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.errorOccurred.emit("Could not open the folder.")

    @Slot(str)
    def openLibraryWindow(self, path):
        file = self._known_file(path)
        if not file:
            return
        manager = self.window.manager
        owner = manager.path_owner(path)
        if owner:
            session = next(
                (s for s in owner.bridge.sessions.values() if s.document.path == path), None
            )
            if session:
                # Ask the owning UI for its current buffer, including unsaved edits.
                owner.bridge.command.emit("detach-request:" + session.document.id)
            else:
                self.errorOccurred.emit("This file is still opening. Try again in a moment.")
            return
        if not file.is_file():
            self.errorOccurred.emit("The file is no longer available.")
            return
        window = manager.window_factory(
            [file], manager.settings_path, manager=manager, restore_session=False
        )
        window.show()
        manager.reveal(window)

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
    def toggleFocusMode(self):
        self.window.set_focus_mode(not self.window.focus_mode)

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
        manager = self.window.manager
        if manager.dragging:
            return
        if (
            document_id not in self.sessions
            or not QApplication.mouseButtons() & Qt.MouseButton.LeftButton
        ):
            self.command.emit("tab-drag-finished")
            return
        drag = QDrag(self.window.view)
        mime = QMimeData()
        mime.setData("application/x-khana-tab", document_id.encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.window.windowIcon().pixmap(32, 32))
        manager.dragging = (self.window, document_id, source, view_state)
        try:
            # A Python application-wide event filter can crash Shiboken while
            # Qt creates/destroys its private drag objects. Let Qt own the drag
            # loop and cancellation; only a released mouse can detach a tab.
            action = drag.exec(Qt.DropAction.MoveAction)
            if (
                action == Qt.DropAction.IgnoreAction
                and not QApplication.mouseButtons() & Qt.MouseButton.LeftButton
                and not self.window.frameGeometry().contains(QCursor.pos())
            ):
                manager.transfer(
                    self.window, document_id, source, view_state, position=QCursor.pos()
                )
        finally:
            manager.dragging = None
            self.command.emit("tab-drag-finished")

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
