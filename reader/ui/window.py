"""Qt window composition and lifetime; document commands live in the bridge."""

import logging

from PySide6.QtCore import QEvent, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QApplication, QMainWindow

from reader import APP_NAME
from reader.diagnostics import configure, monitor
from reader.resources import WEB
from reader.ui.bridge import Bridge
from reader.ui.web import LocalRequests, ReaderPage, ReaderView
from reader.ui.workspace import WindowManager


class ReaderWindow(QMainWindow):
    def __init__(self, initial_paths=(), settings_path=None, manager=None, restore_session=True):
        super().__init__()
        configure(settings_path)
        monitor(QApplication.instance())
        self.manager = manager or WindowManager(settings_path, window_factory=type(self))
        self.manager.windows.append(self)
        self.manager.recent = self
        self.manager.tray.install()
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
        self.bridge.errorOccurred.connect(
            lambda message: logging.getLogger(__name__).warning("Application error: %s", message)
        )
        self.page.renderProcessTerminated.connect(self._renderer_stopped)
        geometry = self.bridge.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("native", self.bridge)
        self.page.setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(str(WEB / "index.html")))

    def _renderer_stopped(self, status, exit_code):
        logging.getLogger(__name__).error(
            "Renderer terminated status=%s exit=%s document=%s",
            status.name,
            exit_code,
            self.bridge.active_id,
        )
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        # Open buffers live in the bridge, so a new page can show them again. Until it
        # is ready, closing the window uses native save prompts (request_exit).
        self.bridge.initialized = False
        if self.close_pending:
            self.close_pending = False
            self.manager.tray.cancel_exit()
        QTimer.singleShot(300, self.view.reload)

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
        if not self.allow_close:
            event.ignore()
            if not self.close_pending:
                self._close_requested()
            return
        self.remember_geometry()
        self.bridge.api_requests.cancel()
        self.bridge.jobs.shutdown()
        self.bridge.spelling.shutdown()
        if self in self.manager.windows:
            self.manager.windows.remove(self)
        if self.manager.recent is self:
            self.manager.recent = self.manager.windows[-1] if self.manager.windows else None
        if self.manager.windows:
            self.manager.windows[-1].bridge.remember_workspace()
        else:
            self.manager.library.shutdown()  # finish queued library writes before exit
        self.manager.tray.window_closed(self)
        logging.getLogger(__name__).info("Window closed")
        super().closeEvent(event)

    def _close_requested(self):
        """Closing the last visible window keeps Khana in the background or quits it.

        Another visible window keeps the application open, so only this window closes,
        after its own unsaved-change checks. Otherwise the remembered choice applies,
        or the page asks, as Bandar does.
        """
        if any(w is not self and w.isVisible() for w in self.manager.windows):
            self.request_exit()
            return
        action = self.bridge.preferences()["closeAction"]
        if action == "background":
            self.manager.tray.background(self)
        elif action == "quit" or not self.bridge.initialized:
            self.manager.tray.quit_all()
        else:
            self.bridge.ask_close()

    def remember_geometry(self):
        self.bridge.settings.setValue("geometry", self.saveGeometry())
        self.bridge.settings.sync()

    def request_exit(self):
        if self.close_pending:
            return
        self.close_pending = True
        if self.bridge.initialized:
            self.bridge.command.emit("quit-request")
            return
        # No page can answer (it is loading, or its renderer stopped): check the
        # buffers natively instead of closing them unseen.
        confirmed = self.bridge.confirm_native_quit()
        self.close_pending = False
        if confirmed:
            self.allow_close = True
            self.close()
        else:
            self.manager.tray.cancel_exit()
