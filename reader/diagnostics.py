"""Bounded local logs, crash traces and event-loop timing for the desktop app."""

from __future__ import annotations

import atexit
import faulthandler
import logging
import sys
import threading
import time
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QTimer, QtMsgType, qInstallMessageHandler, qVersion

from reader import VERSION

_directory = None
_fault_file = None
_heartbeat = None
_previous_qt = None
logger = logging.getLogger("reader")


def configure(settings_path=None):
    global _directory, _fault_file, _previous_qt
    if _directory is not None:
        return _directory
    from reader.ui.settings import default_settings_path

    directory = Path(settings_path or default_settings_path()).parent / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "khana.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        crash = directory / "crash.log"
        if crash.exists() and crash.stat().st_size > 2 * 1024 * 1024:
            crash.replace(directory / "crash.log.1")
        _fault_file = crash.open("a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except OSError:
        logger.exception("Could not initialize diagnostics in %s", directory)
        return None
    _directory = directory
    _previous_qt = qInstallMessageHandler(_qt_message)
    atexit.register(_shutdown)
    previous_exception = sys.excepthook

    def exception_hook(kind, value, traceback):
        logger.critical("Unhandled Python exception", exc_info=(kind, value, traceback))
        previous_exception(kind, value, traceback)

    sys.excepthook = exception_hook
    previous_thread_exception = threading.excepthook

    def thread_exception_hook(args):
        logger.critical(
            "Unhandled thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        previous_thread_exception(args)

    threading.excepthook = thread_exception_hook
    logger.info(
        "Application started version=%s python=%s qt=%s",
        VERSION,
        sys.version.split()[0],
        qVersion(),
    )
    return directory


def _shutdown():
    # Qt can emit messages while Python objects are being finalized. Restore
    # its handler before that phase, and release the fatal-trace descriptor.
    qInstallMessageHandler(_previous_qt)
    if _fault_file:
        faulthandler.disable()
        _fault_file.close()


def _qt_message(kind, context, message):
    level = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }.get(kind, logging.WARNING)
    logger.log(level, "Qt: %s", message)
    if _previous_qt:
        _previous_qt(kind, context, message)
    elif level >= logging.WARNING and sys.stderr:
        sys.stderr.write(message + "\n")


def monitor(app):
    global _heartbeat
    if _heartbeat is not None:
        return
    previous = time.monotonic()

    def tick():
        nonlocal previous
        now = time.monotonic()
        delay = now - previous - 1
        previous = now
        if delay > 0.5:
            logger.warning("Native event loop delayed %.0f ms", delay * 1000)

    _heartbeat = QTimer(app)
    _heartbeat.setInterval(1000)
    _heartbeat.timeout.connect(tick)
    _heartbeat.start()
    app.aboutToQuit.connect(lambda: logger.info("Application shutting down"))


def log_directory():
    return _directory


def measured(operation):
    def decorate(function):
        @wraps(function)
        def run(task, *args, **kwargs):
            started = time.monotonic()
            try:
                return function(task, *args, **kwargs)
            finally:
                elapsed = (time.monotonic() - started) * 1000
                if elapsed >= 100 or operation == "load":
                    logger.info(
                        "Worker %s %.1fms document=%s",
                        operation,
                        elapsed,
                        getattr(
                            task,
                            "document_id",
                            getattr(task, "path", getattr(task, "request", {}).get("id", "")),
                        ),
                    )

        return run

    return decorate
