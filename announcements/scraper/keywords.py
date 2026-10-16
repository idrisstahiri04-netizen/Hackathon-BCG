"""Cheap 'any keyword at all?' pre-filter, used to skip GAA / MyGov pages and KNA summaries
before downloading or analysing them."""
import re
import unicodedata


def _fold(s: str) -> str:
    # "El Niño" -> "el nino", so accented and plain spellings both match
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _words(k: str) -> str:
    return r"[\s-]+".join(re.escape(w) for w in re.split(r"[\s-]+", _fold(k)))


class KeywordTagger:
    def __init__(self, search_terms: list[str], tags: dict[str, list[str]]):
        self.search_terms = search_terms
        # search terms match as word prefixes, like WordPress search ("fertili" -> fertiliser/fertilizer)
        alts = "|".join(_words(k) for k in search_terms + [k for ks in tags.values() for k in ks])
        self._any = re.compile(rf"(?<![a-z])(?:{alts})")

    def has_any(self, *texts: str) -> bool:
        return bool(self._any.search(_fold(" ".join(t or "" for t in texts))))
