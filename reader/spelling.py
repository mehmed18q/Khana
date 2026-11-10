"""Offline Hunspell lookup, with cached results and explicit exception scopes."""

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


class Spelling:
    def __init__(self):
        self.dictionaries = {}
        self.correct = lru_cache(maxsize=20000)(self.correct)
        self.suggestions = lru_cache(maxsize=512)(self.suggestions)

    @staticmethod
    def languages(word):
        if not any("\u0600" <= char <= "\u06ff" for char in word):
            return ("en-US",)
        if any(char in "پچژگکی\u200c" for char in word):
            return ("fa-IR",)
        # Persian and Arabic share many letters. Accept either dictionary, and
        # prefer Arabic suggestions when the word uses distinct Arabic letters.
        return ("ar", "fa-IR") if any(char in "كةىي" for char in word) else ("fa-IR", "ar")

    def dictionary(self, language):
        if language not in self.dictionaries:
            path = WEB / "dictionaries" / language
            with closing(DictionaryReader(str(path) + ".aff")) as source:
                aff, context = readers.read_aff(source)
            with closing(DictionaryReader(str(path) + ".dic", encoding=context.encoding)) as source:
                dic = readers.read_dic(source, aff=aff, context=context)
            self.dictionaries[language] = Dictionary(aff, dic)
        return self.dictionaries[language]

    def correct(self, word):
        if len(word) > 80 or len(word) < 2:
            return True
        return any(self.dictionary(language).lookup(word) for language in self.languages(word))

    def suggestions(self, word):
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
            if len(candidate) > 1 and candidate != word and self.correct(candidate)
        ]
        if quick:
            return quick[:6]
        candidates = [
            islice(self.dictionary(language).suggest(word), 6) for language in self.languages(word)
        ]
        result = []
        for group in zip_longest(*candidates):
            for suggestion in group:
                if suggestion and suggestion not in result:
                    result.append(suggestion)
                    if len(result) == 6:
                        return result
        return result
