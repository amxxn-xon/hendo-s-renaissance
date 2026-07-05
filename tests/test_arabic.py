#!/usr/bin/env python3
"""tests/test_arabic.py — the Arabic backbone, held to the same standard.

    python3 tests/test_arabic.py

Stdlib only, same conventions as test_core.py. Fixtures are data-anchored:
Buckwalter strings are copied verbatim from data/qac/…-0.4.txt lines, and
the expected verse text is *constructed from those strings*, never typed
from memory — the no-fabrication rule applies to test files too. The
transliteration expectations are regression locks on the DRAFT v0 tables:
they pin current behaviour so silent drift is caught, not a claim that the
draft conventions are final.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arabiyya import buckwalter as bw                      # noqa: E402
from arabiyya.backbone import assemble_entries             # noqa: E402
from arabiyya.glosses import CamelGlossIndex, fold         # noqa: E402
from arabiyya.qac import QuranCorpus                       # noqa: E402
from arabiyya.translit_ar import (transliterate_latin_ar,  # noqa: E402
                                  transliterate_malayalam_ar)
from suriyani.backbone import ENTRY_FIELDS                 # noqa: E402
from suriyani.lookup import resolve                        # noqa: E402
from suriyani.translit import RuleTable                    # noqa: E402

QAC = ROOT / "data" / "qac" / "quranic-corpus-morphology-0.4.txt"
DB_AR = ROOT / "data" / "dictionary_ar.db"

_corpus_cache: list[QuranCorpus] = []


def corpus() -> QuranCorpus:
    if not _corpus_cache:
        _corpus_cache.append(QuranCorpus.load(QAC))
    return _corpus_cache[0]


def test_buckwalter_map_and_total_coverage():
    bw.sanity_check()
    n = 0
    for line in open(QAC, encoding="utf-8"):
        if line.startswith(("#", "LOCATION")) or not line.strip():
            continue
        _, form, _, feats = line.rstrip("\r\n").split("\t")
        bw.to_arabic(form)
        for f in feats.split("|"):
            if f.startswith("LEM:"):
                bw.to_arabic(bw.strip_lemma_index(f[4:]))
            elif f.startswith("ROOT:"):
                bw.to_arabic(f[5:])
        n += 1
    assert n == 128219, f"segment count changed: {n}"


def test_corpus_shape_and_basmala():
    q = corpus()
    assert len(q.tokens) == 77429, len(q.tokens)
    assert max(t.chapter for t in q.tokens) == 114
    # (1:1) word forms, verbatim from the file's own lines:
    #   bisomi  {ll~ahi  {lr~aHoma`ni  {lr~aHiymi
    expected = " ".join(bw.to_arabic(s) for s in
                        ("bisomi", "{ll~ahi", "{lr~aHoma`ni", "{lr~aHiymi"))
    ex = q.example_for(q.tokens[0].signature)
    assert ex["text"] == expected, ex["text"]
    assert ex["ref"] == "Qur'an 1:1" and ex["highlight"] == [0]


def test_transliteration_regression_fixtures():
    lat = RuleTable(ROOT / "tables" / "translit_ara_lat.tsv")
    ml = RuleTable(ROOT / "tables" / "translit_ara_ml.tsv")
    fixtures = {                       # BW verbatim from the file → (lat, ml)
        "bisomi": ("bismi", "ബിസ്മി"),
        "{ll~ahi": ("allahi", "അല്ലഹി"),
        "{lr~aHoma`ni": ("arraḥmāni", "അർറഹ്മാനി"),
        "{loHamodu": ("alḥamdu", "അല്ഹമ്ദു"),
        "naEobudu": ("naʿbudu", "നഅ്ബുദു"),
        "qaAluwA@": ("qālū", "ഖാലൂ"),
        "'aAmanuwA@": ("ʾāmanū", "ആമനൂ"),
        "xayorN": ("ḫayrun", "ഖൈറുൻ"),
        "kita`bN": ("kitābun", "കിതാബുൻ"),
        "EalaY`": ("ʿalā", "അലാ"),
        "yawoma": ("yawma", "യൗമ"),
        "ya$aA^'u": ("yašāʾu", "യശാഉ"),
        "maA^": ("mā", "മാ"),
        "<il~aA^": ("ʾillā", "ഇല്ലാ"),
    }
    for src, (exp_lat, exp_ml) in fixtures.items():
        ar = bw.to_arabic(src)
        L = transliterate_latin_ar(ar, lat)
        M = transliterate_malayalam_ar(ar, ml)
        assert not L.unknown and not M.unknown, (src, L.unknown, M.unknown)
        assert L.text == exp_lat, (src, L.text)
        assert M.text == exp_ml, (src, M.text)


def test_gloss_matching_behaviour():
    idx = CamelGlossIndex(ROOT / "data" / "camel" / "camel-msa-glosses.tsv")
    g, p = idx.lookup("كِتَاب", "N")
    assert g == "book" and p[0]["tier"] == "exact", (g, p)
    g, p = idx.lookup("ثُمّ", "CONJ")           # function word: exact-or-nothing
    assert g is None and p == []
    g, p = idx.lookup("ٱللَّه", "PN")
    assert g and "Allah" in g, g
    g, p = idx.lookup("قَالَ", "V")
    assert g and "say" in g and p[0]["tier"] == "folded", (g, p)
    # the fold is a matching key, symmetric across spelling conventions
    assert fold("رَحْمٰن") == fold("رَحْمَان")
    assert fold("ءَامَنَ") == fold("آمَن")


def test_contract_coverage_and_determinism():
    e1, s1 = assemble_entries(ROOT, top_n=20)
    e2, s2 = assemble_entries(ROOT, top_n=20)
    assert e1 == e2 and s1 == s2, "assemble_entries is not deterministic"
    assert all(list(e.keys()) == ENTRY_FIELDS for e in e1)
    assert all(e["headword_eastern"] for e in e1), "vocalised headword missing"
    assert all(e["example_ref"] and e["example_text"] for e in e1)
    assert all(e["headword_eastern"] ==
               unicodedata.normalize("NFC", e["headword_eastern"]) for e in e1)
    assert s1["with_example"] == s1["entries"]


def test_lookup_paths_on_arabic_store():
    if not DB_AR.exists():
        print("  (skipped: run `python3 compile_arabic.py build` first)")
        return
    con = sqlite3.connect(DB_AR)
    con.row_factory = sqlite3.Row

    r = resolve(con, "الله", log_misses=False)          # skeleton
    assert r.kind == "candidates" and r.matched_on == "bare", r.kind
    assert len(r.entries) >= 3                          # the case forms

    voc = r.entries[0]["headword_eastern"]              # paste-vocalised
    r2 = resolve(con, voc, log_misses=False)
    assert r2.kind in ("entry", "candidates") and r2.matched_on == "eastern"

    r3 = resolve(con, "زغغغ", log_misses=False)          # honest miss
    assert r3.kind == "miss"

    r4 = resolve(con, "من", log_misses=False)            # rich ambiguity
    assert r4.kind == "candidates" and len(r4.entries) >= 3
    con.close()


TESTS = [
    test_buckwalter_map_and_total_coverage,
    test_corpus_shape_and_basmala,
    test_transliteration_regression_fixtures,
    test_gloss_matching_behaviour,
    test_contract_coverage_and_determinism,
    test_lookup_paths_on_arabic_store,
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
