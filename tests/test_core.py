#!/usr/bin/env python3
"""Test suite — run from the repo root:  python3 tests/test_core.py

Standard library only, on purpose. Each test is a plain function; the
runner at the bottom finds them, runs them, and exits non-zero on any
failure so this can sit in a git hook or CI later.

Two tests need the built database (data/dictionary.db). If it is missing
they tell you to run `python3 compile.py build` instead of failing
cryptically. The translit test deliberately compares *stored* values
against a *fresh* run of the engines — if someone edits the TSV tables
and forgets to rebuild, that test fails, which is exactly the reminder
they need.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from suriyani import sedra3                              # noqa: E402
from suriyani.lookup import normalise, resolve           # noqa: E402
from suriyani.olam import OlamIndex, pivot               # noqa: E402
from suriyani.translit import (RuleTable,                # noqa: E402
                               transliterate_latin,
                               transliterate_malayalam)

DATA = ROOT / "data" / "sedra3"
DB = ROOT / "data" / "dictionary.db"


# --- anchored to the format documentation itself ---------------------------

def test_unicode_consonant_map() -> None:
    sedra3.unicode_sanity_check()
    # BFBS.README.TXT's own example: the first word of Matthew is "CTBA".
    assert sedra3.to_syriac_consonantal("CTBA") == "\u071f\u072c\u0712\u0710"
    assert sedra3.SEYAME == "\u0308"


def test_doc_morphology_example() -> None:
    # SEDRA3.DOC worked example: 557056 -> gender COMMON, number SINGULAR.
    assert sedra3.decode_word_features(557056) == {
        "gender": "common", "number": "singular"}


def test_bfbs_anchor() -> None:
    # BFBS.README.TXT: word address 33565194 = 0x02002A0A -> record 10762.
    assert 33565194 >> 24 == 0x02
    assert 33565194 & 0xFF_FFFF == 10762
    first = next(sedra3.parse_bfbs(DATA / "BFBS.TXT"))
    assert (first.book, first.chapter, first.verse,
            first.word_pos, first.word_id) == (52, 1, 1, 1, 10762)


def test_parse_counts() -> None:
    # Line counts of the vendored files; a partial copy would show here.
    assert len(sedra3.parse_roots(DATA / "ROOTS.TXT")) == 2050
    assert len(sedra3.parse_lexemes(DATA / "LEXEMES.TXT")) == 3559
    assert len(sedra3.parse_words(DATA / "WORDS.TXT")) == 29699


def test_tokeniser() -> None:
    assert sedra3.tokenize_vocalised("C'T,oB,oA") == ["C'", "T,o", "B,o", "A"]
    assert sedra3.tokenize_vocalised("A_NoA") == ["A_", "No", "A"]


# --- the engines -------------------------------------------------------------

def test_translit_matches_store() -> None:
    """Fresh engine output must equal what compile.py stored.

    Fails when tables/*.tsv changed after the last build — rebuild, then
    rerun the tests.
    """
    if not DB.exists():
        raise AssertionError("data/dictionary.db missing — run: python3 compile.py build")
    lat = RuleTable(ROOT / "tables" / "translit_syr_lat.tsv")
    ml = RuleTable(ROOT / "tables" / "translit_syr_ml.tsv")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for e in con.execute("SELECT sedra3_vocalised, translit_lat, translit_ml FROM entries"):
        L = transliterate_latin(e["sedra3_vocalised"], lat)
        M = transliterate_malayalam(e["sedra3_vocalised"], ml)
        assert L.ok and M.ok, f"unmapped tokens for {e['sedra3_vocalised']!r}"
        assert L.text == e["translit_lat"], (e["sedra3_vocalised"], L.text, e["translit_lat"])
        assert M.text == e["translit_ml"], (e["sedra3_vocalised"], M.text, e["translit_ml"])
        # determinism: a second run agrees with the first
        assert transliterate_latin(e["sedra3_vocalised"], lat).text == L.text
    con.close()


def test_olam_pivot() -> None:
    idx = OlamIndex(ROOT / "data" / "olam" / "olam-enml.tsv")
    hits = pivot(["but"], idx)
    assert hits and all(h["english_key"] == "but" for h in hits)
    assert pivot(["zzzz-no-such-english-word"], idx) == []


# --- lookup ------------------------------------------------------------------

def test_normalise() -> None:
    n = normalise("  xx ܠܗ!! ")
    assert n.typed == "ܠܗ" and n.bare == "ܠܗ"
    n = normalise("ܟܬܒܐ ܕܝܠܝܕܘܬܗ")
    assert n.typed == "ܟܬܒܐ" and n.dropped_words == 1
    assert normalise("nothing syriac here").typed == ""


def test_lookup_paths() -> None:
    if not DB.exists():
        raise AssertionError("data/dictionary.db missing — run: python3 compile.py build")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    before = con.execute("SELECT COUNT(*) FROM misses").fetchone()[0]

    r = resolve(con, "ܕܝܢ", log_misses=False)
    assert r.kind == "entry" and r.entries[0]["word_id"] == 4405

    r = resolve(con, "ܐܡܪ", log_misses=False)
    assert r.kind == "candidates" and len(r.entries) >= 2
    freqs = [e["freq"] for e in r.entries]
    assert freqs == sorted(freqs, reverse=True), "candidates must rank by frequency"

    r = resolve(con, "ܦܝܠܣܘܦܐ", log_misses=False)
    assert r.kind == "miss"

    after = con.execute("SELECT COUNT(*) FROM misses").fetchone()[0]
    assert before == after, "log_misses=False must not write"
    con.close()


# --- runner ------------------------------------------------------------------

def main() -> int:
    from suriyani import make_stdout_utf8_safe
    make_stdout_utf8_safe()  # a failing assert's Syriac repr must not itself crash on Windows
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
