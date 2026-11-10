"""Offline Hunspell lookup, with cached results and explicit exception scopes."""

from contextlib import closing
from functools import lru_cache
from itertools import islice

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

    def dictionary(self, word):
        language = "fa-IR" if any("\u0600" <= char <= "\u06ff" for char in word) else "en-US"
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
        return self.dictionary(word).lookup(word)

    def suggestions(self, word):
        if len(word) > 40:
            return []
        return list(islice(self.dictionary(word).suggest(word), 6))
