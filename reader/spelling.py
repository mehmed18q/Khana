"""Offline Hunspell lookup, with cached results and explicit exception scopes."""

import threading
from contextlib import closing
from functools import lru_cache
from itertools import islice, zip_longest

from spylls.hunspell import Dictionary, readers
from spylls.hunspell.readers.file_reader import FileReader

from reader.resources import WEB


class DictionaryReader(FileReader):
    """Spylls 0.1.7 does not close files when changing the affix encoding."""

    def close(self):
        self.io.close()

    def reset_encoding(self, encoding):
        self.close()
        super().reset_encoding(encoding)


PERSIAN_LETTERS = frozenset("پچژگکی\u200c")
# Letters and vowel marks that Persian text does not use.
ARABIC_MARKS = frozenset("كةىي\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652")


def arabic_text(words) -> bool:
    """Whether some word is unmistakably Arabic."""
    return any(not ARABIC_MARKS.isdisjoint(word) for word in words)


class Spelling:
    """Dictionaries are large (the Arabic one alone takes hundreds of megabytes), so
    one engine serves every window and loads each dictionary at most once."""

    def __init__(self):
        self.dictionaries = {}
        self.lock = threading.RLock()
        self.correct = lru_cache(maxsize=20000)(self.correct)
        self.suggestions = lru_cache(maxsize=512)(self.suggestions)

    @staticmethod
    def languages(word, arabic=False):
        if not any("\u0600" <= char <= "\u06ff" for char in word):
            return ("en-US",)
        if not PERSIAN_LETTERS.isdisjoint(word):
            return ("fa-IR",)
        if not ARABIC_MARKS.isdisjoint(word):
            return ("ar", "fa-IR")
        # Persian and Arabic share many letters. The Arabic dictionary is consulted
        # for such words only in Arabic text.
        return ("fa-IR", "ar") if arabic else ("fa-IR",)

    def dictionary(self, language):
        with self.lock:
            return self._dictionary(language)

    def _dictionary(self, language):
        if language not in self.dictionaries:
            path = WEB / "dictionaries" / language
            with closing(DictionaryReader(str(path) + ".aff")) as source:
                aff, context = readers.read_aff(source)
            with closing(DictionaryReader(str(path) + ".dic", encoding=context.encoding)) as source:
                dic = readers.read_dic(source, aff=aff, context=context)
            self.dictionaries[language] = Dictionary(aff, dic)
        return self.dictionaries[language]

    def correct(self, word, arabic=False):
        if len(word) > 80 or len(word) < 2:
            return True
        with self.lock:
            return any(
                self._dictionary(language).lookup(word) for language in self.languages(word, arabic)
            )

    def suggestions(self, word, arabic=False):
        if len(word) > 40:
            return []
        # Common extra-letter and swapped-letter typos can be resolved with a
        # handful of dictionary lookups. Do not wait for exhaustive suggestions
        # from a second language before showing an already valid correction.
        edits = dict.fromkeys(
            [word[:i] + word[i + 1 :] for i in range(1, len(word)) if word[i] == word[i - 1]]
            + [word[:i] + word[i + 1 :] for i in range(len(word))]
            + [word[:i] + word[i + 1] + word[i] + word[i + 2 :] for i in range(len(word) - 1)]
        )
        quick = [
            candidate
            for candidate in edits
            if len(candidate) > 1 and candidate != word and self.correct(candidate, arabic)
        ]
        if quick:
            return quick[:6]
        with self.lock:
            candidates = [
                islice(self._dictionary(language).suggest(word), 6)
                for language in self.languages(word, arabic)
            ]
            result = []
            for group in zip_longest(*candidates):
                for suggestion in group:
                    if suggestion and suggestion not in result:
                        result.append(suggestion)
                        if len(result) == 6:
                            return result
            return result


_shared = None
_shared_lock = threading.Lock()


def shared_spelling() -> Spelling:
    """The process-wide engine; windows share its dictionaries and caches."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = Spelling()
        return _shared
