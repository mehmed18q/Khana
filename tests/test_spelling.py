"""Dictionary semantics and persistent ignore scopes, without GUI rendering."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings

from reader.spelling import Spelling, arabic_text, shared_spelling
from reader.ui.bridge import Bridge
from reader.ui.spelling import SpellingJobs, Task


class SpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Spelling()

    def test_both_languages_and_inflections(self):
        for word in ("hello", "working", "سلام", "کتاب", "کتاب‌ها"):
            self.assertTrue(self.engine.correct(word), word)
        for word in ("helllo", "سللام"):
            self.assertFalse(self.engine.correct(word), word)
        self.assertIn("hello", self.engine.suggestions("helllo"))
        self.assertEqual(self.engine.suggestions("سللام")[0], "سلام")

    def test_arabic_words_vocalization_and_suggestions(self):
        for word in ("العربية", "المدرسة", "الْعَرَبِيَّة", "كِتَاب", "الكتاب", "مكتبة", "كـتاب"):
            self.assertTrue(self.engine.correct(word), word)
        for word in ("المدررسة", "كتااب"):
            self.assertFalse(self.engine.correct(word), word)
        self.assertEqual(self.engine.suggestions("المدررسة")[0], "المدرسة")

    def test_arabic_dictionary_is_used_only_for_arabic_text(self):
        # Letters shared by Persian and Arabic do not load the large Arabic dictionary.
        self.assertEqual(Spelling.languages("سلاممم"), ("fa-IR",))
        self.assertEqual(Spelling.languages("سلاممم", arabic=True), ("fa-IR", "ar"))
        self.assertEqual(Spelling.languages("كتاب"), ("ar", "fa-IR"))
        self.assertEqual(Spelling.languages("کتاب"), ("fa-IR",))
        self.assertTrue(arabic_text(["سلام", "مدرسة"]))
        self.assertFalse(arabic_text(["سلام", "کتاب"]))
        self.assertIs(shared_spelling(), shared_spelling())
        self.assertIs(SpellingJobs(None).engine, SpellingJobs(None).engine)

    def test_saved_document_and_global_exceptions_survive_restart(self):
        class Harness:
            _spelling_key = Bridge._spelling_key
            _ignored_spelling = Bridge._ignored_spelling
            ignoreSpelling = Bridge.ignoreSpelling

        with tempfile.TemporaryDirectory() as folder:

            def harness():
                obj = Harness()
                obj.settings = QSettings(
                    str(Path(folder) / "settings.ini"), QSettings.Format.IniFormat
                )
                obj.sessions = {
                    name: SimpleNamespace(document=SimpleNamespace(path=path))
                    for name, path in {"one": "/one.md", "two": "/two.md", "draft": ""}.items()
                }
                obj.draft_spelling = {}
                obj.window = SimpleNamespace(manager=SimpleNamespace(windows=[]))
                return obj

            first = harness()
            first.ignoreSpelling("one", "Localword", False)
            first.ignoreSpelling("one", "Globalword", True)
            first.ignoreSpelling("draft", "Draftword", False)
            self.assertIn("draftword", first._ignored_spelling("draft"))
            second = harness()
            self.assertEqual(set(second._ignored_spelling("one")), {"localword", "globalword"})
            self.assertEqual(set(second._ignored_spelling("two")), {"globalword"})

    def test_new_snapshot_cancels_stale_spelling_between_words(self):
        request = {"id": "doc", "token": 1, "kind": "check", "words": ["one", "two"], "ignored": []}
        service = SimpleNamespace(current=request, ready=Mock(), engine=Mock())

        def correct(word, arabic=False):
            service.current = None
            return False

        service.engine.correct.side_effect = correct
        Task(service, request).run()
        service.engine.correct.assert_called_once_with("one", False)
        service.ready.emit.assert_not_called()

    def test_closed_window_rejects_late_spelling_requests(self):
        jobs = SpellingJobs(None)
        jobs.shutdown()
        with patch.object(jobs.pool, "start") as start:
            jobs.submit({"id": "closed", "token": 2, "kind": "check", "words": [], "ignored": []})
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
