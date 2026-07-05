"""Deterministic Arabic transliteration driven by the editable rule tables.

Same philosophy as suriyani/translit.py, one level richer in structure.
The Syriac engine could map SEDRA's vocalised ASCII token-by-token; fully
vocalised Arabic orthography carries structure *between* characters —
matres lectionis (فَا = fā, not fa-ʾ), diphthongs (فَوْ = faw), gemination
(shadda), tanwin — so this engine runs two passes:

  1. tokenise:   base letter + its combining marks; Qur'anic annotation
                 signs and tatweel are dropped (flagged) — recitation
                 apparatus, not lexical content.
  2. normalise:  purely orthographic rewrites, each one definitional in
                 Arabic writing, none of them editorial: dagger alef and
                 fatha+alef → long ā; kasra+bare-yeh → ī; damma+bare-waw
                 → ū; fatha + yeh/waw-with-sukun → ay/aw; tanwin signs →
                 an/in/un (a following bare alef is the tanwin seat and
                 is consumed); shadda → gemination; madda or hamza-above
                 turn their seat into the hamza consonant; a bare alef
                 wasla reads "a" (flagged draft).

Everything that is a *convention* — which Malayalam letter renders ص,
whether ay becomes ൈ — lives in tables/translit_ara_*.tsv, both DRAFT v0,
exactly like the Syriac tables. The engine reports what it cannot map
instead of guessing, and the renderers reuse the Syriac RuleTable loader
and result type, so the shared tail stays shared.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from suriyani.translit import CARRIER, VIRAMA, RuleTable, TranslitResult

from .buckwalter import QURANIC_ANNOTATION

# combining marks we interpret (all verified against unicodedata by the
# buckwalter table's sanity check, which covers the same codepoints)
FATHA, DAMMA, KASRA = "\u064E", "\u064F", "\u0650"
FATHATAN, DAMMATAN, KASRATAN = "\u064B", "\u064C", "\u064D"
SHADDA, SUKUN = "\u0651", "\u0652"
MADDA, HAMZA_ABOVE, DAGGER = "\u0653", "\u0654", "\u0670"
ALEF, ALEF_WASLA, ALEF_MAKSURA = "\u0627", "\u0671", "\u0649"
WAW, YEH, HAMZA, TAA_MARBUTA = "\u0648", "\u064A", "\u0621", "\u0629"
TATWEEL = "\u0640"

_TANWIN = {FATHATAN: "an", DAMMATAN: "un", KASRATAN: "in"}
_SHORT = {FATHA: "a", DAMMA: "u", KASRA: "i"}


@dataclass
class _Tok:
    letter: str            # table key: an Arabic letter, "ة#", " ", "-"
    vowel: str | None      # a i u aa ii uu ay aw an in un | "0" sukun | None bare
    geminate: bool = False


def _tokenize(arabic: str, flags: set[str]) -> list[_Tok]:
    """Pass 1+2 combined: characters → normalised abstract tokens."""
    text = unicodedata.normalize("NFC", arabic)
    raw: list[tuple[str, list[str]]] = []
    for ch in text:
        if ch in QURANIC_ANNOTATION:
            flags.add("quranic-marks-dropped")
            continue
        if ch == TATWEEL:
            continue
        if unicodedata.combining(ch):
            if raw:
                raw[-1][1].append(ch)
            continue
        raw.append((ch, []))

    toks: list[_Tok] = []
    for base, marks in raw:
        if base in " -":
            toks.append(_Tok(base, None))
            continue
        if base == "\u0622":
            # NFC composes ا+ٓ into precomposed آ; undo that so the madda
            # logic below sees the canonical alef+madda sequence.
            base, marks = ALEF, [MADDA] + marks
        letter = base
        vowel: str | None = None
        gem = SHADDA in marks
        if base == ALEF and MADDA in marks:
            # Madda over alef: after a fatha it is the ā mater with a
            # length sign (يَشَآءُ = yašāʾu — the sequence pass folds it);
            # standalone it reads ʾā (the ا table row supplies the hamza).
            vowel = "aa"
        elif HAMZA_ABOVE in marks or MADDA in marks:
            # hamza written as a mark on its seat; madda = hamza + ā
            letter = HAMZA
            if MADDA in marks:
                vowel = "aa"
        if DAGGER in marks:
            vowel = "aa"
        if vowel is None:
            for m in marks:
                if m in _TANWIN:
                    vowel = _TANWIN[m]
                    break
                if m in _SHORT:
                    vowel = _SHORT[m]
                    break
            else:
                vowel = "0" if SUKUN in marks else None
        toks.append(_Tok(letter, vowel, gem))

    # sequence rewrites (orthographic, see module docstring)
    out: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None

        if t.letter == ALEF_WASLA:
            if t.vowel is None:
                t = _Tok(ALEF_WASLA, "a", t.geminate)
                flags.add("wasla-read-as-a")

        # Article-lam assimilation: a bare lam right after word-initial
        # alef wasla, followed by a geminated consonant, is the definite
        # article's lam absorbed into a sun letter (the shadda IS that
        # assimilation in the orthography): ٱللَّهِ -> allāhi,
        # ٱلرَّحْمَٰن -> arraḥmān. Orthographic reading rule, not editorial.
        if (t.letter == "\u0644" and t.vowel is None and not t.geminate
                and out and out[-1].letter == ALEF_WASLA
                and nxt is not None and nxt.geminate):
            flags.add("article-lam-assimilated")
            i += 1
            continue

        # Otiose alef (alef al-wiqāya): the silent alef written after the
        # long-ū plural ending (قَالُوا). Orthographic, carries no sound.
        if (t.letter == ALEF and t.vowel is None
                and out and out[-1].vowel == "uu"):
            flags.add("otiose-alef-dropped")
            i += 1
            continue

        if nxt is not None and not nxt.geminate:
            # long vowels via matres
            if t.vowel == "a" and nxt.letter in (ALEF, ALEF_MAKSURA) \
                    and nxt.vowel in (None, "aa"):
                # bare alef/maksura, or one already carrying the dagger
                out.append(_Tok(t.letter, "aa", t.geminate))
                i += 2
                continue
            if t.vowel == "an" and nxt.letter == ALEF and nxt.vowel is None:
                out.append(t)          # tanwin seat alef: consumed silently
                i += 2
                continue
            if t.vowel == "i" and nxt.letter == YEH and nxt.vowel is None:
                out.append(_Tok(t.letter, "ii", t.geminate))
                i += 2
                continue
            if t.vowel == "u" and nxt.letter == WAW and nxt.vowel is None:
                out.append(_Tok(t.letter, "uu", t.geminate))
                i += 2
                continue
            # diphthongs
            if t.vowel == "a" and nxt.vowel == "0" and nxt.letter in (YEH, WAW):
                out.append(_Tok(t.letter,
                                "ay" if nxt.letter == YEH else "aw",
                                t.geminate))
                i += 2
                continue

        if t.letter == TAA_MARBUTA and t.vowel in (None, "0"):
            out.append(_Tok("ة#", None, t.geminate))
            flags.add("pausal-taa-marbuta")
            i += 1
            continue

        out.append(t)
        i += 1
    return out


def _render(arabic: str, table: RuleTable, malayalam: bool) -> TranslitResult:
    res = TranslitResult(text="")
    toks = _tokenize(arabic, res.flags)
    parts: list[str] = []
    for t in toks:
        if t.letter in " -":
            parts.append(t.letter)
            continue
        cons = table.rules.get(t.letter)
        if cons is None:
            res.unknown.append(t.letter)
            continue

        if malayalam and cons == CARRIER:
            if t.vowel and t.vowel != "0":
                parts.append(table.rules.get("^" + t.vowel, ""))
            else:
                # closed-syllable hamza/ʿayn: Kerala practice writes അ്
                # (cf. the മഅ്ദനി spelling pattern) — draft, flagged in
                # the table header.
                parts.append(table.rules.get("^a", "") + VIRAMA)
            continue

        if malayalam:
            if t.geminate:
                # Geminated r cannot use the virama pattern: റ+്+റ ligates
                # as റ്റ, which Malayalam reads as the ṯṯa cluster. The
                # chillu spelling (ർറ) is how Malayalam writes rr.
                if cons in ("\u0d31", "\u0d30"):        # റ, ര
                    parts.append("\u0d7c" + cons)         # ർ + letter
                else:
                    parts.append(cons + VIRAMA + cons)
            else:
                parts.append(cons)
            if t.vowel in (None, "0"):
                parts.append(VIRAMA)
            elif t.vowel != "a":
                parts.append(table.rules.get(t.vowel, ""))
        else:
            parts.append(cons * 2 if t.geminate else cons)
            if t.vowel and t.vowel != "0":
                parts.append(table.rules.get(t.vowel, ""))
    res.text = "".join(parts)
    return res


def transliterate_latin_ar(arabic: str, table: RuleTable) -> TranslitResult:
    return _render(arabic, table, malayalam=False)


def transliterate_malayalam_ar(arabic: str, table: RuleTable) -> TranslitResult:
    return _render(arabic, table, malayalam=True)
