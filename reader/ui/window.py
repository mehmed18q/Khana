"""Qt window composition and lifetime; document commands live in the bridge."""

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QMainWindow

from reader import APP_NAME
from reader.resources import WEB
from reader.ui.bridge import Bridge
from reader.ui.web import LocalRequests, ReaderPage, ReaderView
from reader.ui.workspace import WindowManager


class ReaderWindow(QMainWindow):
    def __init__(self, initial_paths=(), settings_path=None, manager=None, restore_session=True):
        super().__init__()
        self.manager = manager or WindowManager(settings_path, window_factory=type(self))
        self.manager.windows.append(self)
        self.manager.recent = self
        self.restore_session = restore_session
        self.allow_close = False
        self.close_pending = False
        self.focus_mode = False
        self.before_focus_state = self.windowState()
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
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
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
        if self.focus_mode:
            self.set_focus_mode(False)
            return
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def set_focus_mode(self, enabled):
        if enabled == self.focus_mode:
            return
        self.focus_mode = enabled
        if enabled:
            self.before_focus_state = self.windowState()
            self.showFullScreen()
        else:
            self.setWindowState(self.before_focus_state)
        self.bridge.focusModeChanged.emit(enabled)

    def changeEvent(self, event):
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.focus_mode
            and not self.isFullScreen()
        ):
            self.focus_mode = False
            self.bridge.focusModeChanged.emit(False)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self.manager.recent = self
        super().changeEvent(event)

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
        self.bridge.jobs.shutdown()
        if self in self.manager.windows:
            self.manager.windows.remove(self)
        if self.manager.recent is self:
            self.manager.recent = self.manager.windows[-1] if self.manager.windows else None
        if self.manager.windows:
            self.manager.windows[-1].bridge.remember_workspace()
        super().closeEvent(event)
