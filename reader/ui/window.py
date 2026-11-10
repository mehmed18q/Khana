"""Qt window composition and lifetime; document commands live in the bridge."""

import logging

from PySide6.QtCore import QEvent, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

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
            if self.close_pending:
                return
            self.close_pending = True
            choice = self._close_choice()
            self.close_pending = False
            if choice == "background":
                self.manager.tray.background(self)
            elif choice == "exit":
                self.request_exit()
            return
        self.bridge.settings.setValue("geometry", self.saveGeometry())
        self.bridge.settings.sync()
        self.bridge.api_requests.cancel()
        self.bridge.jobs.shutdown()
        self.bridge.spelling.shutdown()
        if self in self.manager.windows:
            self.manager.windows.remove(self)
        if self.manager.recent is self:
            self.manager.recent = self.manager.windows[-1] if self.manager.windows else None
        if self.manager.windows:
            self.manager.windows[-1].bridge.remember_workspace()
        self.manager.tray.window_closed(self)
        logging.getLogger(__name__).info("Window closed")
        super().closeEvent(event)

    def _close_choice(self):
        language = self.property("language")
        labels = {
            "fa": (
                "بستن خوانا؟",
                "می‌خواهید از برنامه خارج شوید یا در پس‌زمینه بماند؟",
                "خروج",
                "لغو",
                "ماندن در پس‌زمینه",
                "ناحیهٔ آیکون‌های پس‌زمینه در این دسکتاپ در دسترس نیست.",
            ),
            "ar": (
                "إغلاق Khana؟",
                "هل تريد الخروج أم البقاء في الخلفية؟",
                "خروج",
                "إلغاء",
                "البقاء في الخلفية",
                "علبة النظام غير متاحة على سطح المكتب هذا.",
            ),
        }.get(
            language,
            (
                "Close Khana?",
                "Exit the application or keep it running in the background?",
                "Exit",
                "Cancel",
                "Stay in background",
                "The system tray is unavailable on this desktop.",
            ),
        )
        box = QMessageBox(self)
        box.setWindowTitle(labels[0])
        box.setText(labels[1])
        exit_button = box.addButton(labels[2], QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton(labels[3], QMessageBox.ButtonRole.RejectRole)
        background_button = box.addButton(labels[4], QMessageBox.ButtonRole.ActionRole)
        background_button.setEnabled(self.manager.tray.available())
        if not background_button.isEnabled():
            background_button.setToolTip(labels[5])
            box.setInformativeText(labels[5])
        box.setDefaultButton(cancel_button)
        box.setEscapeButton(cancel_button)
        box.exec()
        if box.clickedButton() is exit_button:
            return "exit"
        if box.clickedButton() is background_button:
            return "background"
        return "cancel"

    def request_exit(self):
        if self.close_pending:
            return
        self.close_pending = True
        if self.bridge.initialized:
            self.bridge.command.emit("quit-request")
        else:
            self.allow_close = True
            self.close_pending = False
            self.close()
