"""One tray icon per application, with restore and safe sequential exit."""

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from reader import APP_NAME
from reader.resources import WEB


class TrayController(QObject):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.icon = None
        self.menu = None
        self.exiting = []

    @staticmethod
    def available():
        return QSystemTrayIcon.isSystemTrayAvailable()

    def background(self, window):
        if not self.available():
            return False
        if self.icon is None:
            self.icon = QSystemTrayIcon(QIcon(str(WEB / "icon.svg")), self)
            self.icon.setToolTip(APP_NAME)
            self.menu = QMenu()
            self.open_action = self.menu.addAction("Open")
            self.open_action.triggered.connect(self.restore)
            self.menu.addSeparator()
            self.quit_action = self.menu.addAction("Exit")
            self.quit_action.triggered.connect(self.quit_all)
            self.menu.aboutToShow.connect(self.translate)
            self.icon.setContextMenu(self.menu)
            self.icon.activated.connect(self.activated)
        self.translate()
        self.icon.show()
        QApplication.instance().setQuitOnLastWindowClosed(False)
        window.hide()
        return True

    def translate(self):
        window = self.manager.recent or next(iter(self.manager.windows), None)
        language = window.property("language") if window else "en"
        self.menu.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if language in {"fa", "ar"}
            else Qt.LayoutDirection.LeftToRight
        )
        self.open_action.setText({"fa": "باز کردن", "ar": "فتح"}.get(language, "Open"))
        self.quit_action.setText({"fa": "خروج", "ar": "خروج"}.get(language, "Exit"))

    def activated(self, reason):
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.restore()

    def restore(self):
        for window in self.manager.windows:
            if not window.isVisible():
                window.show()
        target = self.manager.recent or next(iter(self.manager.windows), None)
        if target:
            self.manager.reveal(target)

    def quit_all(self):
        if self.exiting:
            return
        self.exiting = list(self.manager.windows)
        self._next_exit()

    def _next_exit(self):
        self.exiting = [window for window in self.exiting if window in self.manager.windows]
        if self.exiting:
            window = self.exiting[0]
            self.manager.reveal(window)
            window.request_exit()

    def cancel_exit(self):
        self.exiting.clear()

    def window_closed(self, window):
        if window in self.exiting:
            self.exiting.remove(window)
            QTimer.singleShot(0, self._next_exit)
        if not self.manager.windows and self.icon:
            self.icon.hide()
            QApplication.instance().quit()
