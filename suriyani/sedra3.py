"""Faithful reading of the SEDRA III flat-file database.

Everything in this module is anchored to the format documentation that ships
with the data itself:

    data/sedra3/SEDRA3.DOC        (George A. Kiraz, March 1996)
    data/sedra3/BFBS.README.TXT   (same bit layouts, plus the BFBS text format)

Design rule for this file: no linguistic judgement. We convert what SEDRA III
says into Python structures and Unicode, and we stop there. Anything that
would require interpretation (e.g. producing an East Syriac vocalised form
from SEDRA's abstract five-vowel scheme) is deliberately NOT done here —
see DECISIONS.md.

Licence note: SEDRA III is (c) 1996 George A. Kiraz, free for personal and
academic use; publications must carry the acknowledgment formula reproduced
in data/sedra3/SEDRA3.DOC. See README.md § Licences.
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# --------------------------------------------------------------------------
# 1. The SEDRA III ASCII transcription of Syriac
# --------------------------------------------------------------------------
# SEDRA3.DOC, "TRANSCRIPTION OF SYRIAC":
#
#     Consonants: A B G D H O Z K Y ; C L M N S E I / X R W T
#     Vowels:     a o e i u
#     Diacretics: '  dot above, Qushaya
#                 ,  dot below, Rukkakha
#                 _  line under
#                 *  Seyame
#
# The 22 consonant symbols are given in Syriac alphabetical order
# (alaph ... taw), which the DOC confirms via its sorting table
# ("Root: A B G D H O Z K Y ; C L M N S E I / X R W T" -> "a b c ... v").
# We therefore pair them with the 22 letters of the Unicode Syriac block
# in the same order. The unicode_sanity_check() below asserts every
# codepoint against its official Unicode name, so a typo here cannot
# survive the test suite.

_ASCII_CONSONANTS = ["A", "B", "G", "D", "H", "O", "Z", "K", "Y", ";",
                     "C", "L", "M", "N", "S", "E", "I", "/", "X", "R",
                     "W", "T"]

# (codepoint, official Unicode character name) in the same order.
_UNICODE_CONSONANTS = [
    (0x0710, "SYRIAC LETTER ALAPH"),
    (0x0712, "SYRIAC LETTER BETH"),
    (0x0713, "SYRIAC LETTER GAMAL"),
    (0x0715, "SYRIAC LETTER DALATH"),
    (0x0717, "SYRIAC LETTER HE"),
    (0x0718, "SYRIAC LETTER WAW"),
    (0x0719, "SYRIAC LETTER ZAIN"),
    (0x071A, "SYRIAC LETTER HETH"),
    (0x071B, "SYRIAC LETTER TETH"),
    (0x071D, "SYRIAC LETTER YUDH"),
    (0x071F, "SYRIAC LETTER KAPH"),
    (0x0720, "SYRIAC LETTER LAMADH"),
    (0x0721, "SYRIAC LETTER MIM"),
    (0x0722, "SYRIAC LETTER NUN"),
    (0x0723, "SYRIAC LETTER SEMKATH"),
    (0x0725, "SYRIAC LETTER E"),          # ʿē / ayin
    (0x0726, "SYRIAC LETTER PE"),
    (0x0728, "SYRIAC LETTER SADHE"),
    (0x0729, "SYRIAC LETTER QAPH"),
    (0x072A, "SYRIAC LETTER RISH"),
    (0x072B, "SYRIAC LETTER SHIN"),
    (0x072C, "SYRIAC LETTER TAW"),
]

#: SEDRA ASCII consonant -> Unicode Syriac letter
ASCII_TO_SYRIAC: dict[str, str] = {
    a: chr(cp) for a, (cp, _name) in zip(_ASCII_CONSONANTS, _UNICODE_CONSONANTS)
}

#: Seyame (the two-dot plural mark). Unicode has no dedicated Syriac seyame
#: character; established practice — and SEDRA IV's own output, e.g. the API
#: record for a word spelled semkath+gamal+U+0308+... — uses U+0308
#: COMBINING DIAERESIS. We follow that practice.
SEYAME = "\u0308"

#: Compound names in WORDS.TXT join their parts with an ASCII hyphen
#: (e.g. "B;T-IGA"). We keep the hyphen as-is in Unicode output.
_PASSTHROUGH = {"-": "-"}

SEDRA3_VOWELS = set("aoeiu")
SEDRA3_DIACRITICS = {"'": "qushaya", ",": "rukkakha", "_": "linea", "*": "seyame"}


def unicode_sanity_check() -> None:
    """Assert our codepoints against their official Unicode names.

    This is the guard against silent transcription drift: if any entry in
    _UNICODE_CONSONANTS were mistyped, unicodedata would disagree and we
    fail loudly instead of building a corrupt dictionary.
    """
    for cp, expected_name in _UNICODE_CONSONANTS:
        actual = unicodedata.name(chr(cp))
        if actual != expected_name:
            raise AssertionError(
                f"U+{cp:04X}: expected {expected_name!r}, unicodedata says {actual!r}"
            )


def to_syriac_consonantal(ascii_word: str) -> str:
    """Convert a SEDRA III consonantal string (WORDS.TXT field 3) to Unicode.

    This is a pure 1:1 letter substitution — the only kind of Syriac text
    this project ever *produces*, and it is fully determined by SEDRA3.DOC.
    Unknown symbols raise rather than being guessed at.
    """
    out = []
    for ch in ascii_word.strip():
        if ch in ASCII_TO_SYRIAC:
            out.append(ASCII_TO_SYRIAC[ch])
        elif ch == "*":
            out.append(SEYAME)
        elif ch in _PASSTHROUGH or ch == " ":
            # interior spaces occur in two compound proper names
            # (e.g. "XSR;A-DI;L;IOS ", Caesarea Philippi); keep them.
            out.append(ch)
        elif ch in SEDRA3_VOWELS or ch in "',_":
            # Exactly one record in the data (WORDS 2:24690, "B'aMYLLA")
            # carries vocalisation symbols in its consonantal field.
            # Diacritics and vowels contribute no consonant: skip them.
            continue
        else:
            raise ValueError(f"Unexpected symbol {ch!r} in SEDRA consonantal string {ascii_word!r}")
    return "".join(out)


def tokenize_vocalised(vocalised: str) -> list[str]:
    """Split a SEDRA III vocalised string into tokens for the translit engine.

    A token is: one consonant symbol, optionally followed by qushaya/rukkakha/
    linea marks, optionally followed by one vowel — or a bare vowel (initial
    vowels do occur after alaph), or a seyame/hyphen on its own. Example:
        "K'T,oB,oA"  ->  ["K'", "T,o", "B,o", "A"]
    The tokens are looked up in the (human-editable) TSV rule tables; the
    tokeniser itself adds no linguistic content.
    """
    tokens: list[str] = []
    i = 0
    n = len(vocalised)
    while i < n:
        ch = vocalised[i]
        if ch in ASCII_TO_SYRIAC:
            j = i + 1
            while j < n and vocalised[j] in "',_":
                j += 1
            if j < n and vocalised[j] in SEDRA3_VOWELS:
                j += 1
            tokens.append(vocalised[i:j])
            i = j
        elif ch in SEDRA3_VOWELS or ch in "*-":
            tokens.append(ch)
            i += 1
        else:
            raise ValueError(f"Unexpected symbol {ch!r} in vocalised string {vocalised!r}")
    return tokens


# --------------------------------------------------------------------------
# 2. Record parsing
# --------------------------------------------------------------------------
# All five files are one-record-per-line, comma-separated, with strings in
# double quotes. IMPORTANT: quoted strings can contain commas (rukkakha in
# vocalised words, ", " in English meanings), so we must use a real CSV
# reader, never str.split(",").
#
# Field order caveat: SEDRA3.DOC *describes* the 16-bit attributes field
# before the 32-bit morphology field, but in the data files the 32-bit
# value comes first (verified empirically: position-5 values like 7405716
# cannot fit in 16 bits, and the position-6 bit flags line up with the
# documented attribute semantics — e.g. bit 0 SEYAME is set on exactly the
# seven words whose strings contain '*').


def _addr(text: str) -> int | None:
    """'2:100' -> 100. The file id before the colon is redundant per file.

    The data uses the literal string 'NULL' for missing cross-references
    (36 lexemes have no root, 1 word has no lexeme, 229 English meanings
    have no lexeme); we return None for those.
    """
    if text == "NULL":
        return None
    return int(text.split(":")[1])


def _read_rows(path: Path) -> Iterator[list[str]]:
    with open(path, encoding="ascii", newline="") as fh:
        yield from csv.reader(fh)


@dataclass
class Root:
    root_id: int | None
    ascii_form: str
    syriac: str


@dataclass
class Lexeme:
    lexeme_id: int
    root_id: int | None
    ascii_form: str
    syriac: str
    category: str          # decoded from attribute bits 2-5


@dataclass
class Word:
    word_id: int
    lexeme_id: int | None
    ascii_cons: str        # consonantal, SEDRA ASCII
    ascii_voc: str         # vocalised, SEDRA ASCII (abstract 5-vowel scheme)
    syriac_cons: str       # consonantal, Unicode
    features: int          # 32-bit morphology integer (decode with decode_word_features)
    attributes: int        # 16-bit flags
    # convenience flags decoded from `attributes`
    has_seyame: bool = field(init=False)
    is_enclitic: bool = field(init=False)
    is_lexical_form: bool = field(init=False)

    def __post_init__(self) -> None:
        # SEDRA3.DOC, WORDS.TXT attributes: bit 0 seyame, bit 5 enclitic,
        # bit 6 "word represents lexeme" (i.e. this is the citation form).
        self.has_seyame = bool(self.attributes & 0b1)
        self.is_enclitic = bool((self.attributes >> 5) & 0b1)
        self.is_lexical_form = bool((self.attributes >> 6) & 0b1)


@dataclass
class EnglishMeaning:
    meaning_id: int
    lexeme_id: int
    text: str              # "before meaning after (comment)" assembled


@dataclass
class BfbsToken:
    """One running word of the BFBS Peshitta NT text."""
    seq: int               # line number in BFBS.TXT = running position
    book: int              # 52 = Matthew ... 78 = Revelation
    chapter: int
    verse: int
    word_pos: int          # 1-based position within the verse
    word_id: int           # record number in WORDS.TXT


# SEDRA3.DOC lexeme attribute bits 2-5:
LEXEME_CATEGORIES = [
    "verb", "participle adjective", "denominative", "substantive",
    "noun", "pronoun", "proper noun", "numeral", "adjective",
    "particle", "idiom", "adverb (-aʾith)", "adjective of place", "adverb",
]

# Standard 27-book NT order. SEDRA3.DOC only states "52=Matt, 53=Mark,
# 54=Luke, etc."; the continuation is the canonical order, and the per-book
# token counts in BFBS.TXT match it (e.g. 69=Philemon at 277 words,
# 75=2 John at 197, 78=Revelation at 6329). Only Matthew (52) is exercised
# by the v0 pipeline.
BOOK_NAMES = {
    52: "Matthew", 53: "Mark", 54: "Luke", 55: "John", 56: "Acts",
    57: "Romans", 58: "1 Corinthians", 59: "2 Corinthians", 60: "Galatians",
    61: "Ephesians", 62: "Philippians", 63: "Colossians",
    64: "1 Thessalonians", 65: "2 Thessalonians", 66: "1 Timothy",
    67: "2 Timothy", 68: "Titus", 69: "Philemon", 70: "Hebrews",
    71: "James", 72: "1 Peter", 73: "2 Peter", 74: "1 John", 75: "2 John",
    76: "3 John", 77: "Jude", 78: "Revelation",
}


def parse_roots(path: Path) -> dict[int, Root]:
    roots = {}
    for row in _read_rows(path):
        rid = _addr(row[0])
        roots[rid] = Root(rid, row[1], to_syriac_consonantal(row[1]))
    return roots


def parse_lexemes(path: Path) -> dict[int, Lexeme]:
    lexemes = {}
    for row in _read_rows(path):
        lid = _addr(row[0])
        attributes = int(row[4])   # 16-bit value sits last (see caveat above)
        category = LEXEME_CATEGORIES[(attributes >> 2) & 0xF]
        lexemes[lid] = Lexeme(lid, _addr(row[1]), row[2],
                              to_syriac_consonantal(row[2]), category)
    return lexemes


def parse_words(path: Path) -> dict[int, Word]:
    words = {}
    for row in _read_rows(path):
        wid = _addr(row[0])
        words[wid] = Word(
            word_id=wid,
            lexeme_id=_addr(row[1]),
            ascii_cons=row[2],
            ascii_voc=row[3],
            syriac_cons=to_syriac_consonantal(row[2]),
            features=int(row[4]),
            attributes=int(row[5]),
        )
    return words


def parse_english(path: Path) -> dict[int, list[EnglishMeaning]]:
    """Returns lexeme_id -> [EnglishMeaning, ...] preserving file order."""
    by_lexeme: dict[int, list[EnglishMeaning]] = {}
    for row in _read_rows(path):
        mid = _addr(row[0])
        lexeme_id = _addr(row[1])
        if lexeme_id is None:
            continue  # 229 meanings in the data point at no lexeme; unusable here
        meaning, before, after, comment = row[2], row[3], row[4], row[5]
        text = " ".join(p for p in (before, meaning, after) if p).strip()
        if comment:
            text = f"{text} ({comment})"
        by_lexeme.setdefault(lexeme_id, []).append(
            EnglishMeaning(mid, lexeme_id, text))
    return by_lexeme


def parse_bfbs(path: Path) -> Iterator[BfbsToken]:
    """Stream the BFBS NT text. BFBS.README.TXT:

    field 2 is the reference BBCCVVVWW (book/chapter/verse/word),
    field 3 is the word address whose two most significant bytes are
    always 0x02 (= WORDS.TXT); the low 24 bits are the record number.
    """
    for row in _read_rows(path):
        seq = _addr(row[0])
        ref = int(row[1])
        word_addr = int(row[2])
        if word_addr >> 24 != 0x02:
            raise ValueError(f"BFBS line {seq}: word address {word_addr} "
                             f"does not point into WORDS.TXT")
        yield BfbsToken(
            seq=seq,
            book=ref // 10_000_000,
            chapter=(ref // 100_000) % 100,
            verse=(ref // 100) % 1000,
            word_pos=ref % 100,
            word_id=word_addr & 0xFF_FFFF,
        )


# --------------------------------------------------------------------------
# 3. Morphology bitfields (WORDS.TXT features, 32-bit)
# --------------------------------------------------------------------------
# Layout per SEDRA3.DOC / BFBS.README.TXT. The DOC's own worked example —
# 557056 = 0x00088000 -> gender COMMON, number SINGULAR — is a unit test.

_SUFFIX_GENDER = {0: None, 1: "masculine", 2: "feminine"}
_PERSON = {0: None, 1: "third", 2: "second", 3: "first"}
_GENDER = {0: None, 1: "common", 2: "masculine", 3: "feminine"}
_NUMBER = {0: None, 1: "singular", 2: "plural"}
_STATE = {0: None, 1: "absolute", 2: "construct", 3: "emphatic"}
_TENSE = {0: None, 1: "perfect", 2: "imperfect", 3: "imperative",
          4: "infinitive", 5: "active participle", 6: "passive participle",
          7: "participles"}
# Conjugation table transcribed from SEDRA3.DOC (values 0-28). The DOC
# itself lists ETHPALPAL twice (0b010000 and 0b010010); we keep both,
# faithfully.
_CONJUGATION = {
    0: None, 1: "peal", 2: "ethpeal", 3: "pael", 4: "ethpael", 5: "aphel",
    6: "ettaphal", 7: "shaphel", 8: "eshtaphal", 9: "saphel", 10: "estaphal",
    11: "pauel", 12: "ethpaual", 13: "paiel", 14: "ethpaial", 15: "palpal",
    16: "ethpalpal", 17: "palpel", 18: "ethpalpal", 19: "pamel",
    20: "ethpamal", 21: "parel", 22: "ethparal", 23: "pali", 24: "ethpali",
    25: "pahli", 26: "ethpahli", 27: "taphel", 28: "ethaphal",
}


def decode_word_features(features: int) -> dict[str, object]:
    """32-bit WORDS.TXT morphology integer -> readable dict (None fields omitted)."""
    raw = {
        "suffix_gender": _SUFFIX_GENDER.get((features >> 2) & 0b11),
        "suffix_person": _PERSON.get((features >> 4) & 0b11),
        "suffix_number": {0: None, 1: "plural"}.get((features >> 6) & 0b1),
        "suffix_kind": {0: None, 1: "suffix", 2: "contraction"}.get((features >> 7) & 0b11),
        "prefix_code": ((features >> 9) & 0b111111) or None,  # 0-63; SEDRA3.DOC gives no lookup table
        "gender": _GENDER.get((features >> 15) & 0b11),
        "person": _PERSON.get((features >> 17) & 0b11),
        "number": _NUMBER.get((features >> 19) & 0b11),
        "state": _STATE.get((features >> 21) & 0b11),
        "tense": _TENSE.get((features >> 23) & 0b111),
        "conjugation": _CONJUGATION.get((features >> 26) & 0b111111),
    }
    return {k: v for k, v in raw.items() if v is not None}


def morphology_summary(features: int) -> str:
    """One-line human-readable morphology, e.g. 'noun-ish: masculine singular emphatic'."""
    d = decode_word_features(features)
    order = ["conjugation", "tense", "person", "gender", "number", "state",
             "suffix_kind", "suffix_person", "suffix_gender", "suffix_number"]
    parts = []
    for key in order:
        if key in d:
            val = str(d[key])
            if key.startswith("suffix_") and not val.startswith("suffix"):
                val = f"{val} suffix" if key != "suffix_kind" else val
            parts.append(val)
    if "prefix_code" in d:
        parts.append(f"prefix #{d['prefix_code']}")
    return ", ".join(parts)
