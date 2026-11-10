"""Dictionary semantics and persistent ignore scopes, without GUI rendering."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QSettings

from reader.spelling import Spelling
from reader.ui.bridge import Bridge


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
        self.assertIn("سلام", self.engine.suggestions("سللام"))

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


if __name__ == "__main__":
    unittest.main()
