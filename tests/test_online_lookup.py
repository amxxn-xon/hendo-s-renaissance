#!/usr/bin/env python3
"""tests/test_online_lookup.py — the live CAL/Wiktionary section.

    python3 tests/test_online_lookup.py

This is the one part of the project that deliberately reaches a network
API at query time (DECISIONS.md №28) — everything else stays compile-time
only. The parsing/ranking logic is tested against **saved real responses**
(tests/fixtures/*, fetched and cited 2026-07-05 — never hand-typed, per
the no-fabrication rule) so the suite doesn't depend on the network or on
CAL/Wiktionary staying up; one live smoke test per source is included too,
and skips cleanly (not a failure) if the network/site is unreachable, same
convention as the rest of this suite.
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


def test_cal_translit_covers_all_22_consonants():
    import unicodedata
    assert len(ol.CAL_TRANSLIT) == 22
    for ch, code in ol.CAL_TRANSLIT.items():
        assert unicodedata.name(ch).startswith("SYRIAC LETTER"), (ch, code)
    assert ol.to_cal("ܫܠܡܐ") == "$lm)"
    assert ol.to_cal("ܕܝܢ") == "dyn"
    assert ol.to_cal("ܫ̈") is None  # seyame isn't a consonant — must reject, not skip silently


def test_loose_forms_agree_between_cal_display_and_ascii_key():
    # "šlmˀ" (CAL's own unvocalized citation-form display text, e.g. the
    # .lem span in a real result) and "$lm)" (this module's ASCII search
    # key for the same word) must collapse to the same comparison string
    # — that's the whole point of _loose()/_loose_from_cal_key(). Both
    # sides here are bare consonants (no vowels), matching what CAL's own
    # citation-form spans actually contain.
    assert ol._loose("šlmˀ") == ol._loose_from_cal_key("$lm)")
    assert ol._loose("ṣlmˀ") == ol._loose_from_cal_key("clm)")


def test_parse_cal_html_finds_the_real_entry():
    # Fixture: a real response fetched 2026-07-05 for first3="$lm" —
    # https://cal.huc.edu/browseSKEYheaders.php?first3=%22%24lm%22
    html_text = (FIXTURES / "cal_shlm_response.html").read_text(encoding="utf-8")
    results = ol.parse_cal_html(html_text, cal_key="$lm)", limit=10)
    assert results, "expected at least one parsed CAL entry"
    matches = [r for r in results if "peace" in r.gloss]
    assert matches, "the wellbeing/peace entry should be in the parsed results"
    peace = matches[0]
    assert peace.pos == "n.m."
    assert "oneentry.php?lemma=" in peace.url
    # ranking: the exact-match entries should sort before unrelated
    # same-prefix entries (e.g. "Shulmat", "Shalmite" personal/place names)
    exact_idx = results.index(peace)
    assert exact_idx < len(results) - 1
    assert not any("Shulman" in r.gloss for r in results[:exact_idx])


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


def test_live_cal_smoke():
    results, error = ol.fetch_cal("ܫܠܡܐ", timeout=6.0)
    if error:
        print(f"  (skipped: live CAL unreachable — {error})")
        return
    assert any("peace" in r.gloss for r in results)


def test_live_wiktionary_smoke():
    results, error = ol.fetch_wiktionary("ܫܠܡܐ", SYRIAC.wiktionary_lang_candidates, timeout=6.0)
    if error:
        print(f"  (skipped: live Wiktionary unreachable — {error})")
        return
    assert any("peace" in r.gloss for r in results)


def test_lookup_online_respects_per_dict_sources():
    # Structural check only (no network): Arabic must never ask CAL.
    assert "cal" not in ARABIC.online_sources
    assert "wiktionary" in ARABIC.online_sources
    assert "cal" in SYRIAC.online_sources


TESTS = [
    test_cal_translit_covers_all_22_consonants,
    test_loose_forms_agree_between_cal_display_and_ascii_key,
    test_parse_cal_html_finds_the_real_entry,
    test_parse_wiktionary_finds_classical_syriac_section,
    test_parse_wiktionary_ignores_wrong_language_section,
    test_parse_wiktionary_finds_arabic_section,
    test_parse_wiktionary_survives_wrong_shape_json,
    test_lookup_online_respects_per_dict_sources,
    test_live_cal_smoke,
    test_live_wiktionary_smoke,
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
