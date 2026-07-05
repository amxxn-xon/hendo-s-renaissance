#!/usr/bin/env python3
"""tests/test_app.py — smoke tests for the unified Flask app.

    python3 tests/test_app.py

Both dictionaries share one process now (see DECISIONS.md №26): this pins
down that the merge — Blueprints, the header toggle, per-dictionary
keyboards, live suggest — actually works end to end, using Flask's test
client against the real compiled stores. Skips gracefully (not a failure)
when a store hasn't been built yet, same convention as test_core.py and
test_arabic.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as flask_app                                    # noqa: E402

DB_SYR = ROOT / "data" / "dictionary.db"
DB_AR = ROOT / "data" / "dictionary_ar.db"


def client():
    flask_app.app.testing = True
    return flask_app.app.test_client()


def test_root_redirects_to_syriac():
    r = client().get("/")
    assert r.status_code == 302 and r.location.endswith("/syriac/"), r.location


def test_index_pages_render_with_own_branding():
    if not (DB_SYR.exists() and DB_AR.exists()):
        print("  (skipped: build both stores first)")
        return
    c = client()
    for slug, label in (("syriac", b"East Syriac"), ("arabic", b"Arabic")):
        r = c.get(f"/{slug}/")
        assert r.status_code == 200
        assert label in r.data, f"{slug} index missing its own dict_label"


def test_syriac_search_single_and_candidates():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    c = client()
    assert c.get("/syriac/search", query_string={"q": "ܕܝܢ"}).status_code == 200
    r = c.get("/syriac/search", query_string={"q": "ܐܡܪ"})
    assert r.status_code == 200 and b"readings for" in r.data


def test_arabic_search_candidates_and_honest_miss():
    if not DB_AR.exists():
        print("  (skipped: build the Arabic store first)")
        return
    c = client()
    r = c.get("/arabic/search", query_string={"q": "الله"})     # الله
    assert r.status_code == 200 and b"readings for" in r.data
    r = c.get("/arabic/search", query_string={"q": "زغغغ"})     # honest miss
    assert r.status_code == 200 and b"No compiled entry" in r.data


def _min_word_id(db_path: Path) -> int:
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT MIN(word_id) FROM entries").fetchone()[0]
    finally:
        con.close()


def test_entry_ids_are_independent_per_dictionary():
    if not (DB_SYR.exists() and DB_AR.exists()):
        print("  (skipped: build both stores first)")
        return
    # word_id spaces are independent per store (Syriac keeps SEDRA's own
    # record numbers, which don't start at 1 — see dict_registry.py /
    # arabiyya vs suriyani backbones), so pick each store's own valid id.
    c = client()
    r_syr = c.get(f"/syriac/entry/{_min_word_id(DB_SYR)}")
    r_ar = c.get(f"/arabic/entry/{_min_word_id(DB_AR)}")
    assert r_syr.status_code == 200 and r_ar.status_code == 200
    assert r_syr.data != r_ar.data, "different stores must not render identical entries"


def test_suggest_json_is_a_plain_select():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    c = client()
    r = c.get("/syriac/suggest.json", query_string={"q": "ܕ"})
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


def test_keyboards_differ_per_dictionary():
    c = client()
    syr = c.get("/syriac/keyboard.json").get_json()
    ar = c.get("/arabic/keyboard.json").get_json()
    assert syr["letters"] and ar["letters"] and syr["letters"] != ar["letters"]


def test_missing_store_is_a_clean_503_not_a_500_or_stray_file():
    # Regression for the review finding: connect() on an absent store used
    # to mint a zero-byte db file and then 500 on the first query. It must
    # now be a clean 503 with build instructions, and NO file created.
    import pathlib
    from app import StoreNotBuilt, db_for

    class Fake:
        slug = "zzz_test"
        db_filename = "zzz_test_nonexistent.db"
        @property
        def db_path(self):
            return ROOT / "data" / "zzz_test_nonexistent.db"

    fake = Fake()
    assert not fake.db_path.exists()
    raised = False
    with flask_app.app.app_context():
        try:
            db_for(fake)
        except StoreNotBuilt:
            raised = True
    assert raised, "absent store must raise StoreNotBuilt"
    assert not fake.db_path.exists(), "must not create a stray db file"


def test_wrong_script_input_shows_a_notice_not_a_silent_redirect():
    # Regression: an Arabic word pasted into the Syriac dictionary used to
    # bounce silently to the index. It must now render the miss page with
    # a "no Syriac in your search" notice.
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    r = client().get("/syriac/search", query_string={"q": "سلام"})  # Arabic
    assert r.status_code == 200
    assert b"No Syriac in your search" in r.data


def test_lone_vowel_point_does_not_suggest_arbitrary_words():
    # Regression: a combining-mark-only query used to make _near_matches
    # match every stored surface. The miss page must not present the
    # store's most frequent words as "near matches" for a bare vowel point.
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    r = client().get("/syriac/search", query_string={"q": "ܰ"})  # a lone Syriac vowel
    assert r.status_code == 200
    assert b"Near matches in the store" not in r.data


TESTS = [
    test_root_redirects_to_syriac,
    test_index_pages_render_with_own_branding,
    test_syriac_search_single_and_candidates,
    test_arabic_search_candidates_and_honest_miss,
    test_entry_ids_are_independent_per_dictionary,
    test_suggest_json_is_a_plain_select,
    test_keyboards_differ_per_dictionary,
    test_missing_store_is_a_clean_503_not_a_500_or_stray_file,
    test_wrong_script_input_shows_a_notice_not_a_silent_redirect,
    test_lone_vowel_point_does_not_suggest_arbitrary_words,
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
