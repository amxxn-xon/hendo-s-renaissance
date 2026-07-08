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
    """One NT book — or, with book_code=None, the whole Peshitta NT —
    of the BFBS text, indexed for the compiler.

    Loading all of BFBS.TXT costs well under a second for ~110k tokens,
    so we keep it simple and in-memory. Verses are keyed by
    (book, chapter, verse) so multi-book corpora can't collide two books'
    identically-numbered verses.
    """

    def __init__(self, book_code: int | None, tokens: list[BfbsToken]):
        self.book_code = book_code
        self.book_name = (BOOK_NAMES.get(book_code, f"Book {book_code}")
                          if book_code is not None else "Peshitta NT")
        self.tokens = tokens

        #: word_id -> number of running-text occurrences in this corpus
        self.freq: Counter[int] = Counter(t.word_id for t in tokens)

        #: (book, chapter, verse) -> tokens in verse order
        self.verses: dict[tuple[int, int, int], list[BfbsToken]] = defaultdict(list)
        for t in tokens:
            self.verses[(t.book, t.chapter, t.verse)].append(t)
        for vt in self.verses.values():
            vt.sort(key=lambda t: t.word_pos)

        #: word_id -> its earliest token (reading order), and
        #: word_id -> every distinct (book, chapter, verse) it appears in,
        #: in reading order. Both are built in one pass so
        #: attestations_for() is a dict lookup, not a re-scan of ~110k
        #: tokens per entry.
        self.first_seen: dict[int, BfbsToken] = {}
        self.word_verses: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
        _wv_seen: set[tuple[int, int, int, int]] = set()
        for t in sorted(tokens, key=lambda t: (t.book, t.chapter, t.verse, t.word_pos)):
            self.first_seen.setdefault(t.word_id, t)
            key = (t.word_id, t.book, t.chapter, t.verse)
            if key not in _wv_seen:
                _wv_seen.add(key)
                self.word_verses[t.word_id].append((t.book, t.chapter, t.verse))

    @classmethod
    def load(cls, bfbs_path: Path, book_code: int | None = 52) -> "PeshittaBook":
        """book_code=52 loads Matthew (the original scope); book_code=None
        loads every book — the whole Peshitta NT, same vendored file."""
        toks = [t for t in parse_bfbs(bfbs_path)
                if book_code is None or t.book == book_code]
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
        return self._render_verse(t0.book, t0.chapter, t0.verse, word_id, words)

    def _render_verse(self, book: int, chapter: int, verse_no: int,
                      word_id: int, words: dict[int, "Word"]) -> dict:
        verse = self.verses[(book, chapter, verse_no)]
        surface = [words[t.word_id].syriac_cons for t in verse]
        return {
            "ref": f"{BOOK_NAMES.get(book, f'Book {book}')} {chapter}:{verse_no}",
            "text": " ".join(surface),
            "highlight": [i for i, t in enumerate(verse) if t.word_id == word_id],
        }

    def attestations_for(self, word_id: int, words: dict[int, "Word"],
                         limit: int = 20) -> dict:
        """Every verse (up to `limit`) where word_id occurs, in reading
        order — the full concordance for this word within the corpus, same
        consonantal-only rendering as example_for(). Returns
        {"total": N, "shown": [{ref,text,highlight}, ...]}; `total` is the
        true verse count so the UI can say "showing 20 of 333"."""
        verses = self.word_verses.get(word_id, [])
        shown = [self._render_verse(b, c, v, word_id, words)
                 for b, c, v in verses[:limit]]
        return {"total": len(verses), "shown": shown}
