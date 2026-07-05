"""The Peshitta NT as a corpus: frequency, verses, first attestations.

Blueprint anchor: §6.1 step 1 (corpus → frequency list) and the example
field of §6.4. The corpus here is the BFBS Peshitta NT exactly as encoded
in SEDRA III's BFBS.TXT — every running word is a pointer to a WORDS.TXT
record, so frequency counting and concordance lookup need no tokenisation
decisions of our own: we inherit SEDRA's, which were made by its editors.

Frequency is counted over *word records*, not bare strings. Two spellings
that look identical but were analysed differently by SEDRA (different
vocalisation/morphology) count separately; that distinction is exactly
what feeds the ranked-candidates view at lookup time.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from .sedra3 import BOOK_NAMES, BfbsToken, Word, parse_bfbs


class PeshittaBook:
    """One NT book of the BFBS text, indexed for the compiler.

    Loading all of BFBS.TXT and filtering costs well under a second for
    ~110k tokens, so we keep it simple and in-memory.
    """

    def __init__(self, book_code: int, tokens: list[BfbsToken]):
        self.book_code = book_code
        self.book_name = BOOK_NAMES.get(book_code, f"Book {book_code}")
        self.tokens = tokens

        #: word_id -> number of running-text occurrences in this book
        self.freq: Counter[int] = Counter(t.word_id for t in tokens)

        #: (chapter, verse) -> tokens in verse order
        self.verses: dict[tuple[int, int], list[BfbsToken]] = defaultdict(list)
        for t in tokens:
            self.verses[(t.chapter, t.verse)].append(t)
        for vt in self.verses.values():
            vt.sort(key=lambda t: t.word_pos)

        #: word_id -> its earliest token (reading order)
        self.first_seen: dict[int, BfbsToken] = {}
        for t in sorted(tokens, key=lambda t: (t.chapter, t.verse, t.word_pos)):
            self.first_seen.setdefault(t.word_id, t)

    @classmethod
    def load(cls, bfbs_path: Path, book_code: int = 52) -> "PeshittaBook":
        toks = [t for t in parse_bfbs(bfbs_path) if t.book == book_code]
        if not toks:
            raise ValueError(f"No tokens for book code {book_code} in {bfbs_path}")
        return cls(book_code, toks)

    def top(self, n: int) -> list[tuple[int, int]]:
        """The n most frequent word records: [(word_id, count), ...]."""
        return self.freq.most_common(n)

    def example_for(self, word_id: int, words: dict[int, Word]) -> dict | None:
        """First attestation of word_id, as a display-ready example.

        Returns {"ref", "text", "highlight"} where `text` is the whole verse
        in *consonantal* Unicode (space-joined) and `highlight` lists the
        0-based token indices of word_id within it. Consonantal-only is a
        deliberate limit: SEDRA III's vocalisation uses an abstract 5-vowel
        ASCII scheme, and rendering it as East Syriac pointing would require
        editorial decisions we refuse to fake (see DECISIONS.md). The verse
        as consonantal text is faithful to WORDS.TXT as shipped.
        """
        t0 = self.first_seen.get(word_id)
        if t0 is None:
            return None
        verse = self.verses[(t0.chapter, t0.verse)]
        surface = [words[t.word_id].syriac_cons for t in verse]
        return {
            "ref": f"{self.book_name} {t0.chapter}:{t0.verse}",
            "text": " ".join(surface),
            "highlight": [i for i, t in enumerate(verse) if t.word_id == word_id],
        }
