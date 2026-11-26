"""Keep dictionary loading and spelling work off the GUI thread."""

import json
import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from reader.diagnostics import measured
from reader.spelling import arabic_text, shared_spelling


class Task(QRunnable):
    def __init__(self, service, request):
        super().__init__()
        self.service = service
        self.request = request

    @measured("spelling")
    def run(self):
        request = self.request
        if self.service.current is not request:
            return
        result = {"id": request["id"], "token": request["token"], "kind": request["kind"]}
        engine = self.service.engine
        arabic = request.get("language") == "ar"
        try:
            if request["kind"] == "suggest":
                arabic = arabic or arabic_text([request["word"]])
                result["suggestions"] = engine.suggestions(request["word"], arabic)
            else:
                ignored = set(request["ignored"])
                arabic = arabic or arabic_text(request["words"])
                result["misspelled"] = []
                for word in request["words"]:
                    if self.service.current is not request:
                        return
                    if word.casefold() not in ignored and not engine.correct(word, arabic):
                        result["misspelled"].append(word)
        except Exception as error:
            logging.getLogger(__name__).exception(
                "Spelling failed kind=%s document=%s", request["kind"], request["id"]
            )
            result["error"] = str(error)
        if self.service.current is request:
            self.service.ready.emit(json.dumps(result))


class SpellingJobs(QObject):
    ready = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.engine = shared_spelling()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.stopped = False
        self.current = None

    def submit(self, request):
        if self.stopped:
            return
        self.current = request
        self.pool.clear()
        self.pool.start(Task(self, request))

    def shutdown(self):
        self.stopped = True
        self.current = None
        self.pool.clear()
        self.pool.waitForDone()
