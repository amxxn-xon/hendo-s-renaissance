"""QAC extended Buckwalter → Arabic Unicode, verifiably.

This is the Arabic twin of suriyani/sedra3.py's ASCII map, built the same
way: a symbol table paired with official Unicode character names, and a
sanity check that asserts every codepoint against unicodedata at test
time. A typo in the table cannot survive the test suite.

The mapping covers exactly the character set that occurs in
quranic-corpus-morphology-0.4.txt (verified empirically over every FORM,
LEM and ROOT field — see tests). Beyond core Buckwalter it includes the
Qur'anic annotation signs (small high seen, small waw, the sajdah/pause
stops …) that the Uthmani orthography carries inside word forms. The
symbol assignments follow the QAC ecosystem's own published conversion
(mustafa0x/quran-morphology, scripts/bw-to-ar.py, which reproduces the
corpus site's rendering) and are then independently pinned here to Unicode
names.

Nothing in this module interprets anything: it converts an encoding.
"""

from __future__ import annotations

import re
import unicodedata

# (buckwalter symbol, codepoint, official Unicode name)
_TABLE: list[tuple[str, int, str]] = [
    ("'", 0x0621, "ARABIC LETTER HAMZA"),
    (">", 0x0623, "ARABIC LETTER ALEF WITH HAMZA ABOVE"),
    ("&", 0x0624, "ARABIC LETTER WAW WITH HAMZA ABOVE"),
    ("<", 0x0625, "ARABIC LETTER ALEF WITH HAMZA BELOW"),
    ("}", 0x0626, "ARABIC LETTER YEH WITH HAMZA ABOVE"),
    ("A", 0x0627, "ARABIC LETTER ALEF"),
    ("b", 0x0628, "ARABIC LETTER BEH"),
    ("p", 0x0629, "ARABIC LETTER TEH MARBUTA"),
    ("t", 0x062A, "ARABIC LETTER TEH"),
    ("v", 0x062B, "ARABIC LETTER THEH"),
    ("j", 0x062C, "ARABIC LETTER JEEM"),
    ("H", 0x062D, "ARABIC LETTER HAH"),
    ("x", 0x062E, "ARABIC LETTER KHAH"),
    ("d", 0x062F, "ARABIC LETTER DAL"),
    ("*", 0x0630, "ARABIC LETTER THAL"),
    ("r", 0x0631, "ARABIC LETTER REH"),
    ("z", 0x0632, "ARABIC LETTER ZAIN"),
    ("s", 0x0633, "ARABIC LETTER SEEN"),
    ("$", 0x0634, "ARABIC LETTER SHEEN"),
    ("S", 0x0635, "ARABIC LETTER SAD"),
    ("D", 0x0636, "ARABIC LETTER DAD"),
    ("T", 0x0637, "ARABIC LETTER TAH"),
    ("Z", 0x0638, "ARABIC LETTER ZAH"),
    ("E", 0x0639, "ARABIC LETTER AIN"),
    ("g", 0x063A, "ARABIC LETTER GHAIN"),
    ("_", 0x0640, "ARABIC TATWEEL"),
    ("f", 0x0641, "ARABIC LETTER FEH"),
    ("q", 0x0642, "ARABIC LETTER QAF"),
    ("k", 0x0643, "ARABIC LETTER KAF"),
    ("l", 0x0644, "ARABIC LETTER LAM"),
    ("m", 0x0645, "ARABIC LETTER MEEM"),
    ("n", 0x0646, "ARABIC LETTER NOON"),
    ("h", 0x0647, "ARABIC LETTER HEH"),
    ("w", 0x0648, "ARABIC LETTER WAW"),
    ("Y", 0x0649, "ARABIC LETTER ALEF MAKSURA"),
    ("y", 0x064A, "ARABIC LETTER YEH"),
    ("F", 0x064B, "ARABIC FATHATAN"),
    ("N", 0x064C, "ARABIC DAMMATAN"),
    ("K", 0x064D, "ARABIC KASRATAN"),
    ("a", 0x064E, "ARABIC FATHA"),
    ("u", 0x064F, "ARABIC DAMMA"),
    ("i", 0x0650, "ARABIC KASRA"),
    ("~", 0x0651, "ARABIC SHADDA"),
    ("o", 0x0652, "ARABIC SUKUN"),
    ("^", 0x0653, "ARABIC MADDAH ABOVE"),
    ("#", 0x0654, "ARABIC HAMZA ABOVE"),
    ("`", 0x0670, "ARABIC LETTER SUPERSCRIPT ALEF"),
    ("{", 0x0671, "ARABIC LETTER ALEF WASLA"),
    (":", 0x06DC, "ARABIC SMALL HIGH SEEN"),
    ("@", 0x06DF, "ARABIC SMALL HIGH ROUNDED ZERO"),
    ('"', 0x06E0, "ARABIC SMALL HIGH UPRIGHT RECTANGULAR ZERO"),
    ("[", 0x06E2, "ARABIC SMALL HIGH MEEM ISOLATED FORM"),
    (";", 0x06E3, "ARABIC SMALL LOW SEEN"),
    (",", 0x06E5, "ARABIC SMALL WAW"),
    (".", 0x06E6, "ARABIC SMALL YEH"),
    ("!", 0x06E8, "ARABIC SMALL HIGH NOON"),
    ("-", 0x06EA, "ARABIC EMPTY CENTRE LOW STOP"),
    ("+", 0x06EB, "ARABIC EMPTY CENTRE HIGH STOP"),
    ("%", 0x06EC, "ARABIC ROUNDED HIGH STOP WITH FILLED CENTRE"),
    ("]", 0x06ED, "ARABIC SMALL LOW MEEM"),
]

#: buckwalter symbol -> Arabic character
BW_TO_ARABIC: dict[str, str] = {bw: chr(cp) for bw, cp, _ in _TABLE}

#: The Qur'anic annotation signs (recitation / pause / sajdah marks and
#: small letters). They are part of the Uthmani orthography of the word
#: forms, so we render them; but they carry no lexical content, so the
#: search skeleton and the transliterators drop them (with a flag).
QURANIC_ANNOTATION: frozenset[str] = frozenset(
    chr(cp) for _, cp, _ in _TABLE if 0x06DC <= cp <= 0x06ED)

#: Trailing digit on a QAC lemma = homograph sense index (e.g. "EaAd2").
#: Stripped for display and gloss matching; kept in the entry's analysis
#: signature so the two senses stay distinct entries.
_LEMMA_INDEX_RE = re.compile(r"\d+$")


def sanity_check() -> None:
    """Assert every codepoint against its official Unicode name."""
    for bw, cp, expected in _TABLE:
        actual = unicodedata.name(chr(cp))
        if actual != expected:
            raise AssertionError(
                f"{bw!r} -> U+{cp:04X}: expected {expected!r}, "
                f"unicodedata says {actual!r}")


def to_arabic(bw_text: str) -> str:
    """Convert an extended-Buckwalter string to Arabic Unicode, strictly.

    Unknown symbols raise: the mapping was built from the file's actual
    character inventory, so an unknown symbol means the data changed and
    a human should look.
    """
    out = []
    for ch in bw_text:
        if ch == " ":
            # interior spaces occur in one two-word lemma in the data
            # (<ilo yaAsiyna, Q 37:130); keep them.
            out.append(" ")
            continue
        try:
            out.append(BW_TO_ARABIC[ch])
        except KeyError:
            raise ValueError(f"Unmapped Buckwalter symbol {ch!r} in {bw_text!r}") from None
    # NFC: Buckwalter mark order (shadda before its vowel) is not Unicode
    # canonical order; normalising is a canonical-equivalence operation,
    # not an edit — same text, one spelling, so stored forms match what
    # any NFC-normalising input method produces.
    return unicodedata.normalize("NFC", "".join(out))


def strip_lemma_index(bw_lemma: str) -> str:
    return _LEMMA_INDEX_RE.sub("", bw_lemma)


def skeleton(arabic: str) -> str:
    """The consonantal search skeleton of an Arabic string.

    Drops combining marks (harakat, shadda, sukun, madda, dagger alef …),
    the Qur'anic annotation signs, and tatweel — leaving the base letters
    a user would type unvocalised. This is what lookup matches on, the
    exact analogue of the Syriac side's mark-stripping.
    """
    out = "".join(
        ch for ch in unicodedata.normalize("NFC", arabic)
        if not unicodedata.combining(ch)
        and ch not in QURANIC_ANNOTATION
        and ch != "\u0640")
    # Alef wasla is an orthographic refinement no ordinary keyboard types;
    # fold it to plain alef so a user's unvocalised input matches.
    return out.replace("\u0671", "\u0627")
