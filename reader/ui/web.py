"""Offline WebEngine resource policy, navigation and native drop events."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-khana-tab") and self.window.manager.dragging:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.page().runJavaScript("document.body.classList.add('dropping')")
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-khana-tab") and self.window.manager.dragging:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.page().runJavaScript("document.body.classList.remove('dropping')")
        event.accept()

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
