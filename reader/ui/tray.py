"""The tray icon, background mode and the safe, sequential exit of every window.

As in Bandar, the icon is present while Khana runs: a click shows or hides the
windows, and its menu can open a file or quit. In the background, windows are only
hidden, so open documents, unsaved edits and undo history stay as they were.
Without a system tray, opening Khana again from the applications menu brings the
hidden windows back through the single-instance service.
"""

from __future__ import annotations

import shutil

from PySide6.QtCore import QObject, QProcess, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from reader import APP_ID, APP_NAME
from reader.resources import WEB

LABELS = {
    "en": {
        "show": "Show Khana",
        "hide": "Hide window",
        "open": "Open file…",
        "quit": "Quit",
        "background": "Khana keeps your documents open in the background. "
        "Click the tray icon to show it.",
        "background-no-tray": "Khana keeps your documents open in the background. "
        "Open Khana again from the applications menu to show it.",
    },
    "fa": {
        "show": "نمایش خوانا",
        "hide": "پنهان کردن پنجره",
        "open": "باز کردن فایل…",
        "quit": "خروج",
        "background": "خوانا اسنادتان را در پس‌زمینه باز نگه می‌دارد. "
        "برای نمایش، روی آیکون خوانا در سینی سیستم کلیک کنید.",
        "background-no-tray": "خوانا اسنادتان را در پس‌زمینه باز نگه می‌دارد. "
        "برای نمایش، خوانا را دوباره از فهرست برنامه‌ها باز کنید.",
    },
    "ar": {
        "show": "إظهار Khana",
        "hide": "إخفاء النافذة",
        "open": "فتح ملف…",
        "quit": "خروج",
        "background": "يُبقي Khana مستنداتك مفتوحة في الخلفية. انقر أيقونة علبة النظام لإظهاره.",
        "background-no-tray": "يُبقي Khana مستنداتك مفتوحة في الخلفية. "
        "افتح Khana مجددًا من قائمة التطبيقات لإظهاره.",
    },
}


class TrayController(QObject):
    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.icon = None
        self.menu = None
        self.exiting = []
        self.told_about_background = False

    @staticmethod
    def available():
        return QSystemTrayIcon.isSystemTrayAvailable()

    def language(self):
        window = self.manager.recent or next(iter(self.manager.windows), None)
        language = window.property("language") if window else "en"
        return language if language in LABELS else "en"

    def text(self, key):
        return LABELS[self.language()][key]

    def install(self):
        """Show the tray icon for as long as Khana runs, when the desktop has a tray."""
        application = QApplication.instance()
        if self.icon is not None or not isinstance(application, QApplication):
            return
        # Windows hidden in the background must not end the application.
        application.setQuitOnLastWindowClosed(False)
        if not self.available():
            return
        self.icon = QSystemTrayIcon(QIcon(str(WEB / "icon.svg")), self)
        self.icon.setToolTip(APP_NAME)
        self.menu = QMenu()
        self.toggle_action = self.menu.addAction("")
        self.toggle_action.triggered.connect(self.toggle)
        self.open_action = self.menu.addAction("")
        self.open_action.triggered.connect(self.open_file)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction("")
        self.quit_action.triggered.connect(self.quit_all)
        self.menu.aboutToShow.connect(self.translate)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.activated)
        self.translate()
        self.icon.show()

    def translate(self):
        if self.menu is None:
            return
        language = self.language()
        self.menu.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
            if language in {"fa", "ar"}
            else Qt.LayoutDirection.LeftToRight
        )
        self.toggle_action.setText(self.text("hide" if self.any_visible() else "show"))
        self.open_action.setText(self.text("open"))
        self.quit_action.setText(self.text("quit"))

    def any_visible(self):
        return any(w.isVisible() and not w.isMinimized() for w in self.manager.windows)

    def activated(self, reason):
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.toggle()

    def toggle(self):
        if self.any_visible() and any(w.isActiveWindow() for w in self.manager.windows):
            for window in self.manager.windows:
                if window.isVisible():
                    self.background(window, notify=False)
        else:
            self.restore()

    def open_file(self):
        self.restore()
        target = self.manager.recent or next(iter(self.manager.windows), None)
        if target and target.bridge.initialized:
            target.bridge.openFiles()

    def background(self, window, notify=True):
        """Hide a window; its documents and workers keep running."""
        window.remember_geometry()
        window.hide()
        if self.icon:
            self.translate()
        if notify and not self.told_about_background:
            self.told_about_background = True
            self.notify(self.text("background" if self.icon else "background-no-tray"))
        return True

    def notify(self, message):
        """A one-time hint, through the tray or else the desktop notification service."""
        if self.icon:
            self.icon.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 6000)
            return
        program = shutil.which("notify-send")
        if program:
            QProcess.startDetached(
                program,
                [
                    f"--app-name={APP_NAME}",
                    f"--icon={WEB / 'icon.svg'}",
                    f"--hint=string:desktop-entry:{APP_ID}",
                    "--urgency=low",
                    APP_NAME,
                    message,
                ],
            )

    def restore(self):
        for window in self.manager.windows:
            if not window.isVisible():
                window.show()
        target = self.manager.recent or next(iter(self.manager.windows), None)
        if target:
            self.manager.reveal(target)

    def quit_all(self):
        """Close every window in turn; canceling any save prompt stops the exit."""
        if self.exiting or not self.manager.windows:
            return
        # Remember every window's documents before the first one closes.
        self.manager.windows[0].bridge.remember_workspace()
        self.exiting = list(self.manager.windows)
        self._next_exit()

    def _next_exit(self):
        self.exiting = [window for window in self.exiting if window in self.manager.windows]
        if self.exiting:
            window = self.exiting[0]
            self.manager.reveal(window)
            window.request_exit()

    def cancel_exit(self):
        if self.exiting:
            self.exiting.clear()
            if self.manager.windows:
                self.manager.windows[-1].bridge.remember_workspace()

    def window_closed(self, window):
        if window in self.exiting:
            self.exiting.remove(window)
            QTimer.singleShot(0, self._next_exit)
        if not self.manager.windows:
            if self.icon:
                self.icon.hide()
            QApplication.instance().quit()
