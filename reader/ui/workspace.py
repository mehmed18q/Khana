"""Window ownership and acknowledged transfer of document sessions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from reader.editing import EditSession
from reader.ui.tray import TrayController

if TYPE_CHECKING:
    from reader.ui.window import ReaderWindow


@dataclass
class TabTransfer:
    """A transfer retains the origin until the destination acknowledges delivery."""

    origin: ReaderWindow
    document_id: str
    session: EditSession | None = None
    view: dict = field(default_factory=dict)
    delivered: bool = False

    @property
    def prepared(self) -> bool:
        return self.session is not None


class WindowManager(QObject):
    """Own windows and move buffers only after the receiving UI acknowledges them."""

    def __init__(self, settings_path=None, *, window_factory):
        super().__init__()
        self.settings_path = settings_path
        self.window_factory = window_factory
        self.windows = []
        self.recent = None
        self.transfers: dict[tuple[ReaderWindow, str], TabTransfer] = {}
        self.dragging = None
        self.tray = TrayController(self)

    def path_owner(self, path, exclude=None):
        """A queued open reserves its path before the worker finishes loading it."""
        path = str(Path(path).expanduser().resolve())
        for window in self.windows:
            if window is exclude:
                continue
            bridge = window.bridge
            if path in bridge.jobs.loads or any(
                s.document.path == path for s in bridge.sessions.values()
            ):
                return window
            if not bridge.initialized and any(
                str(Path(p).expanduser().resolve()) == path for p in bridge.initial_paths
            ):
                return window
        return None

    def open_paths(self, paths):
        target = self.recent if self.recent in self.windows else next(iter(self.windows), None)
        if target is None:
            target = self.window_factory(paths, self.settings_path, manager=self)
            target.showFullScreen()
            return
        for path in paths:
            resolved = str(Path(path).expanduser().resolve())
            owner = self.path_owner(resolved) or target
            if owner.bridge.initialized:
                owner.bridge.load_paths([Path(resolved)])
            else:
                owner.bridge.initial_paths = [*owner.bridge.initial_paths, Path(resolved)]
            target = owner
        self.reveal(target)

    def reveal(self, window):
        if not window.isVisible():
            window.show()
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()
        self.recent = window

    def is_transferring(self, window, document_id):
        return any(
            t.origin is window and t.document_id == document_id for t in self.transfers.values()
        )

    def has_transfer(self, window):
        return any(
            t.origin is window or target is window for (target, _), t in self.transfers.items()
        )

    def transfer(self, origin, document_id, source, state, target=None, position=None):
        if self.is_transferring(origin, document_id):
            return
        session = origin.bridge.sync_source(document_id, source)
        if not session:
            return
        try:
            view_state = json.loads(state)
            if not isinstance(view_state, dict):
                return
        except ValueError:
            return
        if target and (
            document_id in target.bridge.sessions
            or any(
                s.document.path and s.document.path == session.document.path
                for s in target.bridge.sessions.values()
            )
        ):
            origin.bridge.errorOccurred.emit(
                "That document is already open in the destination window."
            )
            return
        if target is None:
            target = self.window_factory(
                settings_path=self.settings_path, manager=self, restore_session=False
            )
            screen = QApplication.screenAt(position) if position is not None else origin.screen()
            bounds = (screen or origin.screen()).availableGeometry()
            target.resize(origin.size().boundedTo(bounds.size()))
            if position is not None:
                target.move(
                    max(
                        bounds.left(),
                        min(
                            position.x() - target.width() // 3, bounds.right() - target.width() + 1
                        ),
                    ),
                    max(
                        bounds.top(), min(position.y() - 30, bounds.bottom() - target.height() + 1)
                    ),
                )
            target.show()
        self.transfers[target, document_id] = TabTransfer(origin, document_id)
        origin.bridge.command.emit("transfer-started:" + document_id)
        if target.bridge.initialized:
            self.deliver_transfer(target)
        QTimer.singleShot(45000, self, lambda: self.abort_transfer(target, document_id))
        self.reveal(target)

    def prepare_transfer(self, origin, document_id, source, view_state):
        for (target, identifier), transfer in list(self.transfers.items()):
            if identifier != document_id or transfer.origin is not origin or transfer.prepared:
                continue
            try:
                state = json.loads(view_state)
                if not isinstance(state, dict):
                    raise ValueError("Invalid tab state")
            except ValueError:
                self.abort_transfer(target, document_id)
                return
            session = origin.bridge.sync_source(document_id, source)
            if not session:
                self.abort_transfer(target, document_id)
                return
            transfer.session = copy.deepcopy(session)
            transfer.view = state
            if target.bridge.initialized:
                self.deliver_transfer(target)

    def deliver_transfer(self, target):
        for (window, document_id), transfer in list(self.transfers.items()):
            if window is not target or transfer.delivered:
                continue
            if not transfer.prepared:
                target.bridge.command.emit("tab-transfer-wait")
                continue
            transfer.delivered = True
            target.bridge.sessions[document_id] = transfer.session
            payload = transfer.session.payload()
            payload["viewState"] = transfer.view
            target.bridge.documentLoaded.emit(json.dumps(payload, ensure_ascii=False))

    def finish_transfer(self, target, document_id):
        transfer = self.transfers.get((target, document_id))
        if not transfer or not transfer.delivered:
            return
        del self.transfers[target, document_id]
        origin = transfer.origin
        origin.bridge.release_session(document_id)
        origin.bridge.remember_workspace()
        target.bridge.publish_library()
        if not origin.bridge.sessions and not origin.bridge.jobs.loads:
            origin.allow_close = True
            origin.close()

    def abort_transfer(self, target, document_id):
        transfer = self.transfers.pop((target, document_id), None)
        if transfer:
            if transfer.delivered:
                target.bridge.release_session(document_id)
            transfer.origin.bridge.command.emit("transfer-failed:" + document_id)
            transfer.origin.bridge.errorOccurred.emit(
                "Could not move the tab. It is still open in its original window."
            )
