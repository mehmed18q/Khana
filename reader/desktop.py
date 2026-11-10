"""Desktop entry point: parse arguments and compose the application services."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from reader import APP_ID, APP_NAME, VERSION
from reader.instance import SingleInstance
from reader.resources import WEB
from reader.ui.window import ReaderWindow
from reader.ui.workspace import WindowManager


def main():
    parser = argparse.ArgumentParser(
        description="Khana — Local Markdown and HTML reader for Persian, Arabic and English"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument("files", nargs="*", type=Path, help="Markdown or HTML files to open")
    args = parser.parse_args()
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(APP_NAME)
    QApplication.setApplicationVersion(VERSION)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    app.setApplicationDisplayName(APP_NAME)
    # Wayland app_id must match the installed .desktop basename. The desktop
    # shell reads the human-readable Name and themed Icon from that entry.
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(WEB / "icon.svg")))
    instance = SingleInstance(app)
    try:
        if not instance.start_or_forward(args.files):
            return 0
    except RuntimeError as error:
        QMessageBox.warning(None, APP_NAME, str(error))
        return 1
    manager = WindowManager(window_factory=ReaderWindow)
    instance.openRequested.connect(manager.open_paths)
    app.aboutToQuit.connect(instance.close)
    window = ReaderWindow(args.files, manager=manager)
    window.showFullScreen()
    return app.exec()
