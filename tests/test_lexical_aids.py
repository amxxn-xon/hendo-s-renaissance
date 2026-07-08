#!/usr/bin/env python3
"""tests/test_lexical_aids.py — the Lexical Aids coverage boost, held to
the same standard as every other source in this repo.

    python3 tests/test_lexical_aids.py

Own suite, like test_arabic.py/test_app.py — keeps test_core.py's "must
stay 9/9" invariant intact rather than growing that number (assistance.md).

Fixtures are ref numbers into the real vendored PDF
(data/lexical_aids/lexical-aids-3rd-ed-2024.pdf), not typed-from-memory
strings — the no-fabrication rule applies to test files too, and the only
way to honestly test a PDF-extraction pipeline is against the real PDF.
Ref numbers and their known-good/known-bad status were verified empirically
this session (see DECISIONS.md №27 and data/lexical_aids/PROVENANCE.md):

    ref 1   ܠ            "to, for"        — single clean word, no marks lost
    ref 12  ܟܽܘܠ،ܟܽܠ      "all, every"     — two alternate forms, both clean
    ref 3   (qamats only) "no, not"        — base consonant lost to font
                                             corruption; combining-mark-only
    ref 44  ܣܰΏ...ܐ        "much, many"     — a stray Greek glyph mid-word
                                             (verified: entry never even
                                             clears the parse boundary check)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from suriyani import lexical_aids as la                    # noqa: E402
from suriyani import sedra3                                # noqa: E402
from suriyani.backbone import assemble_entries              # noqa: E402
from suriyani.corpus import PeshittaBook                    # noqa: E402

PDF = ROOT / "data" / "lexical_aids" / "lexical-aids-3rd-ed-2024.pdf"


def test_pdf_present_and_sane():
    if not PDF.exists():
        print("  (skipped: data/lexical_aids/lexical-aids-3rd-ed-2024.pdf missing)")
        return
    la.sanity_check(PDF)  # raises on page-count/heading drift


def test_parser_accepts_clean_entries():
    if not PDF.exists():
        print("  (skipped: PDF missing)")
        return
    entries = {e.ref_no: e for e in la.parse_word_frequency_list(PDF)}
    e1 = entries[1]
    assert e1.clean and e1.skeletons == ("ܠ",) and e1.freq_nt == 4234, e1

    e12 = entries[12]
    assert e12.clean and e12.skeletons == ("ܟܘܠ", "ܟܠ") and e12.freq_nt == 1400, e12


def test_parser_rejects_corrupted_entries():
    if not PDF.exists():
        print("  (skipped: PDF missing)")
        return
    entries = {e.ref_no: e for e in la.parse_word_frequency_list(PDF)}
    # ref 3: extraction survives only as a combining mark — no base letter,
    # so it must be flagged unclean with an empty skeleton, not guessed.
    assert 3 in entries and not entries[3].clean and entries[3].skeletons == ()
    # ref 44: a stray Greek glyph mid-word fails the parse boundary check
    # entirely — it must not appear in the results at all (not even marked
    # unclean), since the parser can't be sure where the word actually ends.
    assert 44 not in entries


def test_skeleton_matches_sedra_headword_bare_convention():
    # skeleton_of() must agree with how sedra3/backbone derive headword_bare
    # (combining marks stripped), so the two are directly comparable.
    assert la.skeleton_of("ܕ݁ܶܝܢ") == "ܕܝܢ"


def test_match_against_sedra_is_conservative():
    if not PDF.exists():
        print("  (skipped: PDF missing)")
        return
    d = ROOT / "data" / "sedra3"
    words = sedra3.parse_words(d / "WORDS.TXT")
    matthew = PeshittaBook.load(d / "BFBS.TXT", book_code=52)
    entries = la.parse_word_frequency_list(PDF)
    matched, stats = la.match_against_sedra(entries, words, matthew)
    assert stats["parsed"] == len(entries)
    assert stats["corrupted"] + stats["matched_words"] + stats["unmatched"] == len(entries)
    # every matched word_id must actually be attested in Matthew — the
    # guarantee that lets every added entry keep a real example sentence
    assert all(matthew.freq.get(wid, 0) >= 1 for wid in matched)


def test_assemble_entries_augments_and_cites_correctly():
    """The end-to-end regression test — and the fix for a real bug caught
    this session: a word already in Matthew's native top_n (word_id 4405,
    ܕܝܢ) must NOT get an "_selection" provenance note, even though it also
    appears in the Lexical Aids list — that note must only ever appear on
    entries that wouldn't have been compiled without it (word_id 254, ܐܘ,
    "or" — Matthew freq 1, but 296x across the whole NT per ref #63)."""
    if not PDF.exists():
        print("  (skipped: PDF missing)")
        return
    entries, stats = assemble_entries(ROOT, top_n=150, use_lexical_aids=True)
    assert len(entries) > 150, "lexical aids should widen the store beyond top_n"
    assert stats["with_example"] == stats["entries"], \
        "every entry, including lexical-aids-added ones, needs a real example"

    by_id = {e["word_id"]: e for e in entries}
    assert 254 in by_id, "ܐܘ (or) should be pulled in via Lexical Aids"
    assert "_selection" in by_id[254]["provenance"]
    assert "Lexical Aids" in by_id[254]["provenance"]

    assert 4405 in by_id, "ܕܝܢ is natively in Matthew's own top 150"
    assert "_selection" not in by_id[4405]["provenance"], (
        "a native top-150 entry must not carry a Lexical Aids selection "
        "note, even if it also happens to appear in that book's list")

    baseline, _ = assemble_entries(ROOT, top_n=150, use_lexical_aids=False)
    assert len(baseline) == 150, "--no-lexical-aids must reproduce the old behaviour exactly"


TESTS = [
    test_pdf_present_and_sane,
    test_parser_accepts_clean_entries,
    test_parser_rejects_corrupted_entries,
    test_skeleton_matches_sedra_headword_bare_convention,
    test_match_against_sedra_is_conservative,
    test_assemble_entries_augments_and_cites_correctly,
]

if __name__ == "__main__":
    from suriyani import make_stdout_utf8_safe
    make_stdout_utf8_safe()
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"ok  {t.__name__}")
        except AssertionError as exc:
            print(f"FAIL {t.__name__}: {ascii(str(exc))}")
        except Exception as exc:  # env errors (missing db, moved fixture) must not abort the run
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {ascii(str(exc))}")
    print(f"{passed}/{len(TESTS)} passed")
    sys.exit(0 if passed == len(TESTS) else 1)
