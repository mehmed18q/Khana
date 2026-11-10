"""Offline WebEngine resource policy, navigation and native drop events."""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMenu

from reader.documents import IMAGE_EXTENSIONS
from reader.resources import WEB


class LocalRequests(QWebEngineUrlRequestInterceptor):
    """Allow bundled assets and local images; block every remote resource request."""

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
    def javaScriptConsoleMessage(self, level, message, line, source):
        severity = (
            logging.ERROR
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel
            else logging.WARNING
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel
            else logging.INFO
        )
        logging.getLogger(__name__).log(
            severity, "JavaScript %s:%s %s", source, line, message[:4000]
        )

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.isLocalFile() and Path(url.toLocalFile()).resolve() == WEB / "index.html":
            return True
        if navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme() in {"https", "http", "mailto"}:
                QDesktopServices.openUrl(url)
        return False


class ReaderView(QWebEngineView):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def contextMenuEvent(self, event):
        request = self.lastContextMenuRequest()
        if not request or not (request.isContentEditable() or request.selectedText()):
            return
        menu = QMenu(self)
        persian = self.window.property("language") == "fa"
        arabic = self.window.property("language") == "ar"
        menu.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if persian or arabic else Qt.LayoutDirection.LeftToRight
        )
        if request.misspelledWord():
            suggestions = request.spellCheckerSuggestions()
            for word in suggestions[:8]:
                action = menu.addAction(word)
                action.triggered.connect(
                    lambda checked=False, value=word: self.page().replaceMisspelledWord(value)
                )
            if not suggestions:
                menu.addAction(
                    "پیشنهادی پیدا نشد"
                    if persian
                    else "لا توجد اقتراحات إملائية"
                    if arabic
                    else "No spelling suggestions"
                ).setEnabled(False)
            menu.addSeparator()
        for name, english, farsi, arabic_label in (
            ("Undo", "Undo", "واگرد", "تراجع"),
            ("Redo", "Redo", "انجام دوباره", "إعادة"),
            ("Cut", "Cut", "برش", "قص"),
            ("Copy", "Copy", "کپی", "نسخ"),
            ("Paste", "Paste", "چسباندن", "لصق"),
            ("SelectAll", "Select all", "انتخاب همه", "تحديد الكل"),
        ):
            native = self.page().action(getattr(QWebEnginePage.WebAction, name))
            action = menu.addAction(farsi if persian else arabic_label if arabic else english)
            action.setEnabled(native.isEnabled())
            action.triggered.connect(native.trigger)
        menu.exec(event.globalPos())
        menu.deleteLater()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-khana-tab") and self.window.manager.dragging:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.page().runJavaScript("document.body.classList.add('dropping')")
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-khana-tab") and self.window.manager.dragging:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.page().runJavaScript("document.body.classList.remove('dropping')")
        if self.window.manager.dragging:
            event.accept()
        else:
            super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.page().runJavaScript("document.body.classList.remove('dropping')")
        if event.mimeData().hasFormat("application/x-khana-tab") and self.window.manager.dragging:
            origin, document_id, source, state = self.window.manager.dragging
            if origin is not self.window:
                self.window.manager.transfer(origin, document_id, source, state, target=self.window)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.window.bridge.load_paths(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
