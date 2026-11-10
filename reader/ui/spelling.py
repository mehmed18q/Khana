"""Keep dictionary loading and spelling work off the GUI thread."""

import json

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from reader.spelling import Spelling


class Task(QRunnable):
    def __init__(self, service, request):
        super().__init__()
        self.service = service
        self.request = request

    def run(self):
        request = self.request
        result = {"id": request["id"], "token": request["token"], "kind": request["kind"]}
        try:
            if request["kind"] == "suggest":
                result["suggestions"] = self.service.engine.suggestions(request["word"])
            else:
                ignored = set(request["ignored"])
                result["misspelled"] = [
                    word
                    for word in request["words"]
                    if word.casefold() not in ignored and not self.service.engine.correct(word)
                ]
        except Exception as error:
            result["error"] = str(error)
        self.service.ready.emit(json.dumps(result))


class SpellingJobs(QObject):
    ready = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.engine = Spelling()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)

    def submit(self, request):
        self.pool.clear()
        self.pool.start(Task(self, request))

    def shutdown(self):
        self.pool.clear()
        self.pool.waitForDone()
