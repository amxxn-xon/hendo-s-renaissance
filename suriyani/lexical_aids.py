"""Lexical Aids to the Syriac New Testament — a prioritization signal,
never a text source.

See data/lexical_aids/PROVENANCE.md for the licensing/authorization status
(a proprietary Gorgias Press work, used under an attested IIT Goa
partnership, flagged for Dr. Amaldev to attach the written agreement) and
the full safety rationale, summarized here: this module NEVER stores or
displays a single character of the book's own extracted Syriac text. It
only decides which additional SEDRA III word-records (suriyani/sedra3.py)
are worth compiling beyond Matthew's own frequency cutoff, by matching the
book's Chapter 1 (Word Frequency List — ranked by frequency across the
*whole* Peshitta NT) back onto SEDRA's own verbatim consonantal forms.
Every extracted Syriac span is validated character-by-character against
the Syriac Unicode block before it's used for anything; anything that
fails is dropped, never corrected by guessing (project rule: never invent
source-language text).

Parsing is deliberately conservative. This PDF has verified font-encoding
corruption (~11% of Chapter 1 entries — see PROVENANCE.md): a blob that
doesn't parse unambiguously is skipped as an honest gap rather than
rescued by a cleverer regex. False negatives here just mean a word misses
the coverage boost this pass; false positives would mean a fabricated
match, which is the one failure mode this module must never produce.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_CH1_START_RE = re.compile(r"Chapter\s+1\s*\n\s*Word Frequency List")
_CH2_START_RE = re.compile(r"Chapter\s+2\s*\n\s*Proper Noun Frequency List")

#: Repeating running headers / column headers to strip before entry-splitting
#: — all clean Latin text, matched against the extracted pages, not guessed.
_NOISE_LINE_RES = [
    re.compile(r"^\d+\.\s*Word Frequency List\s*$"),
    re.compile(r"^\d+$"),                               # bare page numbers
    re.compile(r"^Syriac$"), re.compile(r"^Cat\.$"), re.compile(r"^Meaning$"),
    re.compile(r"^Words occurring .* times?\.?$"),
    re.compile(r"^How to Use the Frequency List\.?$"),
    re.compile(r"^Sequence\.?$"), re.compile(r"^Format\.?$"),
]

_ENTRY_START_RE = re.compile(r"(?:^|\n)(\d+)\.\s*")
#: The leading span right after "NN." — one or more Syriac letters/marks,
#: possibly several alternate forms joined by the book's Arabic-comma
#: separator (e.g. "ܟܽܘܠ،ܟܽܠ" = "all, every" / "all-inclusive"). The range
#: boundaries were confirmed character-by-character against ord()/
#: unicodedata.name() (U+0700 SYRIAC LETTER ALAPH's block start … U+074F
#: block end, U+0300 … U+036F combining marks, U+060C ARABIC COMMA) —
#: not assumed from how they render here.
_SYRIAC_RUN_RE = re.compile("^([܀-ݏ̀-ͯ،]+)")
_TRAILING_FREQ_RE = re.compile(r"\((\d[\d,]*)\)\s*$")


def _is_clean_syriac(s: str) -> bool:
    """Every character must be a Syriac letter or a combining mark, AND at
    least one must be an actual base letter — a form that survives
    extraction as only a stray combining mark (observed: entry 3, a
    qamats/zqapha with its base consonant lost to font corruption) has an
    empty skeleton once marks are stripped, which is a gap, not a word."""
    bare = s.replace("،", "").strip()
    if not bare:
        return False
    if not all(0x0700 <= ord(ch) <= 0x074F or unicodedata.combining(ch)
              for ch in bare):
        return False
    return bool(skeleton_of(bare))


def skeleton_of(syriac: str) -> str:
    """Bare consonantal skeleton — mirrors how SEDRA III's own
    headword_bare is derived, so the two are directly comparable."""
    return "".join(ch for ch in syriac if not unicodedata.combining(ch))


@dataclass(frozen=True)
class LexicalAidEntry:
    ref_no: int
    syriac_raw: str               # as extracted; kept only for the audit trail
    skeletons: tuple[str, ...]    # validated candidate skeleton(s)
    freq_nt: int                  # frequency across the whole Peshitta NT
    clean: bool                   # every candidate skeleton passed validation?


def sanity_check(pdf_path: Path) -> None:
    """Catch silent drift if a different edition/printing gets dropped in."""
    import fitz
    doc = fitz.open(pdf_path)
    if len(doc) < 200:
        raise AssertionError(f"expected a ~227pp edition, got {len(doc)} pages")
    full_text = "\n".join(p.get_text() for p in doc)
    if not _CH1_START_RE.search(full_text):
        raise AssertionError("Chapter 1 (Word Frequency List) heading not found")
    if not _CH2_START_RE.search(full_text):
        raise AssertionError("Chapter 2 (Proper Noun Frequency List) heading not found")


def _extract_section1_text(pdf_path: Path) -> str:
    import fitz
    doc = fitz.open(pdf_path)
    full = "\n".join(p.get_text() for p in doc)
    start = _CH1_START_RE.search(full)
    end = _CH2_START_RE.search(full)
    if not (start and end and start.start() < end.start()):
        raise AssertionError("could not locate Chapter 1 bounds in the PDF")
    return full[start.end():end.start()]


def _strip_noise(text: str) -> str:
    lines = [l for l in text.split("\n")
            if not any(rx.match(l.strip()) for rx in _NOISE_LINE_RES)]
    return "\n".join(lines)


def parse_word_frequency_list(pdf_path: Path) -> list[LexicalAidEntry]:
    """Chapter 1 → entries. Conservative: a blob that doesn't match cleanly
    is skipped, not force-parsed (see module docstring)."""
    section = _strip_noise(_extract_section1_text(pdf_path))
    marks = list(_ENTRY_START_RE.finditer(section))
    entries: list[LexicalAidEntry] = []
    for i, m in enumerate(marks):
        ref_no = int(m.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(section)
        blob = section[m.end():end]
        freq_m = _TRAILING_FREQ_RE.search(blob.strip())
        syr_m = _SYRIAC_RUN_RE.match(blob)
        if not (freq_m and syr_m):
            continue
        # The run stops at the first non-Syriac character, which in a
        # well-formed entry is where the category abbreviation begins
        # (plain ASCII, e.g. "v.", "prep.", "n. m.", "particle"). If a
        # font-corrupted glyph (observed: stray Greek letters) sits inside
        # the word instead, the run stops there too — but the character
        # right after it won't be plain ASCII. That's the signal used to
        # tell a legitimate truncation from a corrupted one, without
        # needing to parse the category itself.
        next_ch = blob[syr_m.end():syr_m.end() + 1]
        if next_ch and not (next_ch.isascii() and (next_ch.isalpha() or next_ch in "/(\n ")):
            continue
        try:
            freq_nt = int(freq_m.group(1).replace(",", ""))
        except ValueError:
            continue
        raw = syr_m.group(1).strip()
        forms = [f for f in raw.split("،") if f.strip()]
        clean = bool(forms) and all(_is_clean_syriac(f) for f in forms)
        skeletons = tuple(skeleton_of(f) for f in forms if _is_clean_syriac(f))
        entries.append(LexicalAidEntry(ref_no=ref_no, syriac_raw=raw,
                                       skeletons=skeletons, freq_nt=freq_nt,
                                       clean=clean))
    return entries


def match_against_sedra(entries: list[LexicalAidEntry], words: dict,
                        matthew) -> tuple[dict[int, LexicalAidEntry], dict]:
    """-> ({word_id: matching LexicalAidEntry}, stats).

    Only clean, validated skeletons that are also attested at least once in
    the compiled corpus (Matthew) are matched, so every word added this way
    still gets a genuine first-attestation example — the entry shape never
    changes for these entries, no null-example special case needed.
    """
    by_skeleton: dict[str, list[int]] = {}
    for wid, w in words.items():
        by_skeleton.setdefault(w.syriac_cons, []).append(wid)

    matched: dict[int, LexicalAidEntry] = {}
    stats = {"parsed": len(entries), "corrupted": 0, "matched_words": 0,
             "unmatched": 0}
    for e in entries:
        if not e.clean or not e.skeletons:
            stats["corrupted"] += 1
            continue
        hit = False
        for sk in e.skeletons:
            for wid in by_skeleton.get(sk, ()):
                if matthew.freq.get(wid, 0) >= 1:
                    matched.setdefault(wid, e)
                    hit = True
        if hit:
            stats["matched_words"] += 1
        else:
            stats["unmatched"] += 1
    return matched, stats
