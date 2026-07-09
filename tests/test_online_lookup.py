#!/usr/bin/env python3
"""tests/test_online_lookup.py — the live Wiktionary/Wikidata section.

    python3 tests/test_online_lookup.py

This is the one part of the project that deliberately reaches a network
API at query time (DECISIONS.md №28, widened in №33) — everything else
stays compile-time only. The parsing/filtering logic is tested against
**saved real responses** (tests/fixtures/*, fetched and cited 2026-07-05
and 2026-07-07 — never hand-typed, per the no-fabrication rule) so the
suite doesn't depend on the network or on the sites staying up; one live
smoke test per source is included too, and skips cleanly (not a failure)
if the network/site is unreachable, same convention as the rest of this
suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import online_lookup as ol                                  # noqa: E402
from dict_registry import ARABIC, SYRIAC                    # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


# --- Wiktionary: exact entry ------------------------------------------------

def test_parse_wiktionary_finds_classical_syriac_section():
    # Fixture: real action=parse response for page=ܫܠܡܐ, fetched 2026-07-05
    data = json.loads((FIXTURES / "wiktionary_shlomo_syr.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_json(data, ("Classical Syriac", "Syriac"), "ܫܠܡܐ")
    assert results, "Classical Syriac section should be found and yield glosses"
    assert "peace" in results[0].gloss
    assert results[0].url.endswith("wiki/%DC%AB%DC%A0%DC%A1%DC%90") or "wiki/" in results[0].url


def test_parse_wiktionary_ignores_wrong_language_section():
    # The same page also has an "Assyrian Neo-Aramaic" section (a distinct
    # language) — asking only for "Classical Syriac"/"Syriac" must not
    # accidentally pick that one up instead.
    data = json.loads((FIXTURES / "wiktionary_shlomo_syr.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_json(data, ("Nonexistent Language",), "ܫܠܡܐ")
    assert results == []


def test_parse_wiktionary_finds_arabic_section():
    # Fixture: real action=parse response for page=سلام, fetched 2026-07-05
    data = json.loads((FIXTURES / "wiktionary_salam_ar.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_json(data, ("Arabic",), "سلام")
    assert results, "Arabic section should be found and yield glosses"
    assert "peace" in results[0].gloss


def test_parse_wiktionary_survives_wrong_shape_json():
    # Regression: a captive portal / proxy can return valid JSON of the
    # wrong shape (null, a number, a list, {"parse": null}) with HTTP 200.
    # The parser must return [] for all of them, never raise — otherwise
    # the whole /online.json route 500s.
    for bad in [None, 42, "text", [], {}, {"parse": None},
                {"parse": {"wikitext": 5}}, {"error": "missingtitle"}]:
        assert ol.parse_wiktionary_json(bad, ("Arabic",), "x") == [], bad


def test_parse_wiktionary_surfaces_related_language_sections():
    # The real ܫܠܡܐ page carries four Aramaic-family sections (verified
    # 2026-07-08 against the saved fixture): Classical Syriac plus the
    # related Assyrian Neo-Aramaic, Turoyo, and Western Neo-Aramaic. With
    # the related pattern, all should surface — Classical Syriac FIRST,
    # each labelled with its own section name.
    data = json.loads((FIXTURES / "wiktionary_shlomo_syr.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_json(
        data, ("Classical Syriac", "Syriac"), "ܫܠܡܐ",
        related_pattern=SYRIAC.wiktionary_related_pattern)
    assert len(results) >= 2, "related Aramaic sections should widen the results"
    assert results[0].pos == "Classical Syriac", "own language must rank first"
    assert any(r.pos == "Assyrian Neo-Aramaic" for r in results)
    # And the Arabic page: dialects kept, Persian/Urdu/Ottoman never leak.
    data = json.loads((FIXTURES / "wiktionary_salam_ar.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_json(
        data, ("Arabic",), "سلام",
        related_pattern=ARABIC.wiktionary_related_pattern)
    assert results and results[0].pos == "Arabic"
    assert all(r.pos.endswith("Arabic") for r in results)


# --- Wiktionary: related-pages search ---------------------------------------

def test_parse_wiktionary_search_widens_and_drops_exact_page():
    # Fixture: real list=search response for srsearch=سلام, fetched 2026-07-07
    data = json.loads((FIXTURES / "wiktionary_search_salam_ar.json").read_text(encoding="utf-8"))
    results = ol.parse_mw_search_json(data, "سلام", "en.wiktionary.org",
                                      drop_exact=True)
    assert results, "search should surface related pages"
    # The exact page is covered by the exact-entry source, so it's dropped
    # from the wider net to avoid duplication.
    assert all(r.headword != "سلام" for r in results)
    # Snippets are HTML-stripped (the API wraps matches in <span>).
    assert all("<span" not in r.gloss and "</span>" not in r.gloss for r in results)


def test_parse_wiktionary_search_works_for_syriac_too():
    data = json.loads((FIXTURES / "wiktionary_search_shlomo_syr.json").read_text(encoding="utf-8"))
    results = ol.parse_mw_search_json(data, "ܫܠܡܐ", "en.wiktionary.org",
                                      drop_exact=True)
    assert results, "Syriac full-text search should return related pages"
    assert all(r.url.startswith("https://en.wiktionary.org/wiki/") for r in results)


def test_parse_wikipedia_search_keeps_the_exact_article():
    # Fixtures: real list=search responses from the languages' own
    # Wikipedias, fetched 2026-07-09. Unlike Wiktionary's wider-net use,
    # the exact article IS the prize here, so it must be kept — and links
    # must go to that wiki, not en.wiktionary.
    data = json.loads((FIXTURES / "wikipedia_search_shlomo_syr.json").read_text(encoding="utf-8"))
    results = ol.parse_mw_search_json(data, "ܫܠܡܐ", "arc.wikipedia.org")
    assert results and any(r.headword == "ܫܠܡܐ" for r in results)
    assert all(r.url.startswith("https://arc.wikipedia.org/wiki/") for r in results)
    data = json.loads((FIXTURES / "wikipedia_search_salam_ar.json").read_text(encoding="utf-8"))
    results = ol.parse_mw_search_json(data, "سلام", "ar.wikipedia.org")
    assert results and any(r.headword == "سلام" for r in results)


def test_parse_wiktionary_search_survives_wrong_shape_json():
    for bad in [None, 42, [], {}, {"query": None}, {"query": {"search": 5}},
                {"query": {"search": [None, 7, "x"]}}]:
        assert ol.parse_mw_search_json(bad, "x", "en.wiktionary.org") == [], bad


# --- Wiktionary: English -> target translations ------------------------------

def test_parse_translations_finds_arabic_for_flower():
    # Fixture: real action=parse response for the English page "flower",
    # fetched 2026-07-09. Its Translations table carries Arabic entries;
    # Classical Syriac has none there — an honest empty, not an error.
    data = json.loads((FIXTURES / "wiktionary_flower_en.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_translations_json(data, ("ar",), "flower")
    assert results, "Arabic translations of 'flower' should be found"
    assert all(r.pos == "Arabic" for r in results)
    assert all("flower" in r.gloss for r in results)
    assert ol.parse_wiktionary_translations_json(
        data, ("syc", "aii", "tru"), "flower") == []


def test_parse_translations_reads_subpage_tt_templates():
    # Fixture: the house/translations subpage (fetched 2026-07-09), which
    # uses {{tt|…}}/{{tt+|…}} templates and parks the primary sense under
    # a {{trans-top-see|…}} block — both must parse.
    data = json.loads((FIXTURES / "wiktionary_house_translations_en.json").read_text(encoding="utf-8"))
    results = ol.parse_wiktionary_translations_json(data, ("ar",), "house")
    assert len(results) >= 3, "the primary-sense Arabic words must surface"
    assert any("abode" in r.gloss for r in results), \
        "sense line from the trans-top-see block should be attributed"


def test_parse_translations_survives_wrong_shape_json():
    for bad in [None, 42, [], {}, {"parse": None}, {"parse": {"wikitext": 5}}]:
        assert ol.parse_wiktionary_translations_json(bad, ("ar",), "x") == [], bad


def test_lookup_online_english_reports_one_labelled_source():
    import online_lookup as m
    saved = m.fetch_wiktionary_translations
    try:
        m.fetch_wiktionary_translations = lambda *a, **k: ([], None)
        out = m.lookup_online_english(ARABIC, "flower")
        assert [s["id"] for s in out["sources"]] == ["wiktionary_translations"]
        assert "flower" in out["sources"][0]["label"]
        assert "Arabic" in out["sources"][0]["label"]
    finally:
        m.fetch_wiktionary_translations = saved


# --- Wikidata lexemes -------------------------------------------------------

def test_parse_wikidata_lexemes_keeps_only_target_language():
    # Fixture: real wbsearchentities lexeme search for سلام, fetched
    # 2026-07-07. It contains Arabic AND New Persian lexemes of the same
    # spelling; the Arabic dictionary must keep only the Arabic ones.
    data = json.loads((FIXTURES / "wikidata_lex_salam_ar.json").read_text(encoding="utf-8"))
    results = ol.parse_wikidata_lexemes_json(data, ("Arabic",))
    assert results, "Arabic lexemes should be found"
    assert all(r.gloss == "Arabic" for r in results), \
        "New Persian / other-language lexemes must be filtered out"
    # Part of speech is pulled from the '<lang>, <pos>' description.
    assert any(r.pos for r in results)
    # Protocol-relative URLs are made absolute.
    assert all(r.url.startswith("https://") for r in results if r.url)


def test_parse_wikidata_lexemes_empty_for_sparse_syriac():
    # Fixture: real (empty) lexeme search for ܫܠܡܐ — Classical Syriac
    # lexemes are sparse on Wikidata. An empty search list is a clean [].
    data = json.loads((FIXTURES / "wikidata_lex_shlomo_syr.json").read_text(encoding="utf-8"))
    assert ol.parse_wikidata_lexemes_json(data, ("Classical Syriac", "Syriac")) == []


def test_parse_wikidata_lexemes_survives_wrong_shape_json():
    for bad in [None, 42, [], {}, {"search": None}, {"search": 5},
                {"search": [None, 7, {"description": 3}]}]:
        assert ol.parse_wikidata_lexemes_json(bad, ("Arabic",)) == [], bad


# --- config / orchestration -------------------------------------------------

def test_cal_is_gone_and_sources_are_configured_per_dict():
    assert "cal" not in SYRIAC.online_sources
    assert "cal" not in ARABIC.online_sources
    # Wiktionary (both forms) and each language's own Wikipedia serve both
    # dictionaries; Wikidata lexemes are Arabic-only.
    for cfg in (SYRIAC, ARABIC):
        assert "wiktionary" in cfg.online_sources
        assert "wiktionary_search" in cfg.online_sources
        assert "wikipedia" in cfg.online_sources
    assert SYRIAC.wikipedia_host == "arc.wikipedia.org"
    assert ARABIC.wikipedia_host == "ar.wikipedia.org"
    assert "wikidata" not in SYRIAC.online_sources
    assert "wikidata" in ARABIC.online_sources


def test_lookup_online_reports_every_configured_source():
    # No network: monkeypatch the fetchers to deterministic empties, and
    # confirm the orchestration reports one block per configured source in
    # order, each with a label.
    import online_lookup as m
    saved = (m.fetch_wiktionary, m.fetch_wiktionary_search,
             m.fetch_wikipedia_search, m.fetch_wikidata_lexemes)
    try:
        m.fetch_wiktionary = lambda *a, **k: ([], None)
        m.fetch_wiktionary_search = lambda *a, **k: ([], None)
        m.fetch_wikipedia_search = lambda *a, **k: ([], None)
        m.fetch_wikidata_lexemes = lambda *a, **k: ([], None)
        out = m.lookup_online(ARABIC, "سلام")
        # sources is an ordered list; ids appear in cfg.online_sources order.
        assert [s["id"] for s in out["sources"]] == list(ARABIC.online_sources)
        assert all(s["label"] for s in out["sources"])
    finally:
        (m.fetch_wiktionary, m.fetch_wiktionary_search,
         m.fetch_wikipedia_search, m.fetch_wikidata_lexemes) = saved


# --- live smoke tests (skip cleanly offline) --------------------------------

def test_live_wiktionary_smoke():
    results, error = ol.fetch_wiktionary("ܫܠܡܐ", SYRIAC.wiktionary_lang_candidates, timeout=6.0)
    if error:
        print(f"  (skipped: live Wiktionary unreachable — {error})")
        return
    assert any("peace" in r.gloss for r in results)


def test_live_wikidata_smoke():
    results, error = ol.fetch_wikidata_lexemes("سلام", ARABIC.wikidata_lang_labels, timeout=6.0)
    if error:
        print(f"  (skipped: live Wikidata unreachable — {error})")
        return
    assert all(r.gloss == "Arabic" for r in results)


TESTS = [
    test_parse_wiktionary_finds_classical_syriac_section,
    test_parse_wiktionary_ignores_wrong_language_section,
    test_parse_wiktionary_finds_arabic_section,
    test_parse_wiktionary_survives_wrong_shape_json,
    test_parse_wiktionary_surfaces_related_language_sections,
    test_parse_wiktionary_search_widens_and_drops_exact_page,
    test_parse_wiktionary_search_works_for_syriac_too,
    test_parse_wikipedia_search_keeps_the_exact_article,
    test_parse_wiktionary_search_survives_wrong_shape_json,
    test_parse_translations_finds_arabic_for_flower,
    test_parse_translations_reads_subpage_tt_templates,
    test_parse_translations_survives_wrong_shape_json,
    test_lookup_online_english_reports_one_labelled_source,
    test_parse_wikidata_lexemes_keeps_only_target_language,
    test_parse_wikidata_lexemes_empty_for_sparse_syriac,
    test_parse_wikidata_lexemes_survives_wrong_shape_json,
    test_cal_is_gone_and_sources_are_configured_per_dict,
    test_lookup_online_reports_every_configured_source,
    test_live_wiktionary_smoke,
    test_live_wikidata_smoke,
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
        except Exception as exc:  # env errors (missing db, network) must not abort the run
            print(f"ERROR {t.__name__}: {type(exc).__name__}: {ascii(str(exc))}")
    print(f"{passed}/{len(TESTS)} passed")
    sys.exit(0 if passed == len(TESTS) else 1)
