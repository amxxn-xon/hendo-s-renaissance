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
    assert r.status_code == 200 and b"Not in the dictionary yet" in r.data


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
    assert b"Nothing matched" in r.data and b"Syriac" in r.data


def test_lone_vowel_point_does_not_suggest_arbitrary_words():
    # Regression: a combining-mark-only query used to make _near_matches
    # match every stored surface. The miss page must not present the
    # store's most frequent words as "near matches" for a bare vowel point.
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    r = client().get("/syriac/search", query_string={"q": "ܰ"})  # a lone Syriac vowel
    assert r.status_code == 200
    assert b"Close matches" not in r.data


def test_browse_lists_entries_and_clamps_bad_pages():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    c = client()
    r = c.get("/syriac/browse")
    assert r.status_code == 200 and b"All entries" in r.data
    # Out-of-range / junk paging must clamp, never 500.
    assert c.get("/syriac/browse", query_string={"page": "9999"}).status_code == 200
    assert c.get("/syriac/browse", query_string={"page": "zzz",
                                                 "order": "alpha"}).status_code == 200


def test_random_redirects_to_a_compiled_entry():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    r = client().get("/syriac/random")
    assert r.status_code == 302 and "/syriac/entry/" in r.location, r.location


def test_roots_page_renders_for_both_dictionaries():
    if not (DB_SYR.exists() and DB_AR.exists()):
        print("  (skipped: build both stores first)")
        return
    c = client()
    for slug in ("syriac", "arabic"):
        r = c.get(f"/{slug}/roots")
        assert r.status_code == 200 and b"Root tree" in r.data, slug
        assert b"rt-" in r.data, f"{slug} roots page has no root anchors"
        # The index is a scannable chip grid — no embedded graph here
        # (Ameen: the family map lives on entry pages and root cards).
        assert b'id="root-graph"' not in r.data, slug
    # QAC assigns no roots to function words: the Arabic tree must say so
    # honestly instead of pretending full coverage.
    assert b"carry no root" in c.get("/arabic/roots").data


def test_root_card_renders_graph_data_and_404s_on_unknown_root():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    root_id = con.execute(
        "SELECT root_id FROM entries WHERE root IS NOT NULL AND root != '' "
        "ORDER BY freq DESC LIMIT 1").fetchone()[0]
    con.close()
    c = client()
    r = c.get(f"/syriac/root/{root_id}")
    assert r.status_code == 200
    # The graph's data island and its container must both be there, and
    # the plain list fallback too (the graph is progressive enhancement).
    assert b'id="graph-data"' in r.data and b'id="root-graph"' in r.data
    assert b"as a list" in r.data
    assert c.get("/syriac/root/999999999").status_code == 404


def test_homepage_common_words_skip_function_words():
    # The highlight filter is a POS-category rule (app._CONTENT_POS_WHERE),
    # never a typed word list. Check it against the real stores: it must
    # leave no function-word POS in the top-12 and must not empty the list.
    import sqlite3
    from app import _CONTENT_POS_WHERE, _FUNCTION_POS
    dbs = [p for p in (DB_SYR, DB_AR) if p.exists()]
    if not dbs:
        print("  (skipped: build a store first)")
        return
    for db_path in dbs:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT pos FROM entries WHERE {_CONTENT_POS_WHERE} "
            "ORDER BY freq DESC LIMIT 12").fetchall()
        con.close()
        assert rows, f"{db_path.name}: filter emptied the highlight list"
        for r in rows:
            assert not any(p in (r["pos"] or "") for p in _FUNCTION_POS), \
                f"{db_path.name}: function word leaked through: {r['pos']}"
    assert client().get("/syriac/").status_code == 200


def test_entry_shows_full_attestations_for_frequent_words():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import json as _json
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT word_id, freq, attestations FROM entries "
        "ORDER BY freq DESC LIMIT 1").fetchone()
    con.close()
    att = _json.loads(row["attestations"] or "{}")
    # A frequent word must carry many attestations (capped) and the true
    # total, and the entry page must offer the collapsible concordance.
    assert att.get("total", 0) > 1, "frequent word should attest in many verses"
    assert att.get("shown"), "attestations must include rendered verses"
    assert len(att["shown"]) <= att["total"], "shown can't exceed total"
    r = client().get(f"/syriac/entry/{row['word_id']}")
    assert r.status_code == 200
    assert b"more-attest" in r.data, "collapsible concordance should render"


def test_lemma_page_lists_the_whole_paradigm():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    row = con.execute(
        "SELECT lexeme_id, COUNT(*) n FROM entries WHERE lexeme_id IS NOT NULL "
        "GROUP BY lexeme_id HAVING n > 1 ORDER BY n DESC LIMIT 1").fetchone()
    con.close()
    if not row:
        print("  (skipped: no multi-form lexeme in store)")
        return
    lexeme_id, n = row
    c = client()
    r = c.get(f"/syriac/lemma/{lexeme_id}")
    assert r.status_code == 200 and b"Every form in this dictionary" in r.data
    assert b"dictionary form" in r.data, "citation form should be marked"
    assert c.get("/syriac/lemma/99999999").status_code == 404


def test_transliteration_search_finds_entries_both_scripts():
    if not (DB_SYR.exists() and DB_AR.exists()):
        print("  (skipped: build both stores first)")
        return
    import sqlite3
    c = client()
    # Pull a real stored Latin transliteration from each store and search
    # by it — never a form typed from memory (rule #1).
    for slug, db in (("syriac", DB_SYR), ("arabic", DB_AR)):
        con = sqlite3.connect(db)
        lat = con.execute(
            "SELECT translit_lat FROM entries "
            "WHERE translit_lat != '' ORDER BY freq DESC LIMIT 1").fetchone()[0]
        con.close()
        r = c.get(f"/{slug}/search", query_string={"q": lat})
        assert r.status_code == 200, (slug, lat)
        # It resolves to a real entry or candidate list, not the miss page.
        assert b"Not in the dictionary yet" not in r.data, (slug, lat)
        assert (b"transliteration" in r.data      # single entry: context line
                or b"spelled like" in r.data      # candidates: translit heading
                or b"readings for" in r.data), (slug, lat)


def test_transliteration_suggest_offers_latin_hits():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    lat = con.execute("SELECT translit_lat FROM entries WHERE translit_lat != '' "
                      "ORDER BY freq DESC LIMIT 1").fetchone()[0]
    con.close()
    # First two letters of a real stored transliteration must autocomplete.
    r = client().get("/syriac/suggest.json", query_string={"q": lat[:2]})
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list) and data, "Latin prefix should suggest something"


def test_english_meaning_search_finds_entries():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import re as _re
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    # Data-anchored: take the first ≥4-letter word of a real stored gloss
    # and search by it — the meaning tier must find that entry, never 404
    # into the miss page.
    gloss = con.execute("SELECT gloss_en FROM entries WHERE gloss_en IS NOT NULL "
                        "AND gloss_en != '' ORDER BY freq DESC LIMIT 1").fetchone()[0]
    con.close()
    word = next(w for w in _re.findall(r"[a-z]+", gloss.lower()) if len(w) >= 4)
    r = client().get("/syriac/search", query_string={"q": word})
    assert r.status_code == 200
    assert b"Not in the dictionary yet" not in r.data, (gloss, word)
    assert b"English meaning" in r.data or b"meaning" in r.data, word


def test_translit_query_with_extra_suffix_still_matches():
    if not DB_AR.exists():
        print("  (skipped: build the Arabic store first)")
        return
    import sqlite3
    import unicodedata
    from suriyani.lookup import _DIGRAPH_MAP
    con = sqlite3.connect(DB_AR)
    # "baytun for bayt": take a real stored transliteration and type it
    # with one extra trailing letter — the reverse-prefix tier must still
    # reach the word instead of declaring a miss.
    lat = con.execute("SELECT translit_lat FROM entries WHERE length(translit_lat) >= 5 "
                      "ORDER BY freq DESC LIMIT 1").fetchone()[0]
    con.close()
    typed = "".join(_DIGRAPH_MAP.get(ch, ch) for ch in lat)
    typed = "".join(ch for ch in unicodedata.normalize("NFD", typed)
                    if not unicodedata.combining(ch) and ch.isascii() and ch.isalnum())
    typed += "n"
    r = client().get("/arabic/search", query_string={"q": typed})
    assert r.status_code == 200
    assert b"Not in the dictionary yet" not in r.data, (lat, typed)


def test_english_digraph_transcription_finds_entries():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import sqlite3
    from suriyani.lookup import _DIGRAPH_MAP
    con = sqlite3.connect(DB_SYR)
    # Data-anchored: take a real stored transliteration containing š and
    # retype it the way an English speaker would (š→sh …, drop diacritics)
    # using the app's own digraph map — never a form typed from memory.
    lat = con.execute("SELECT translit_lat FROM entries WHERE translit_lat "
                      "LIKE '%š%' ORDER BY freq DESC LIMIT 1").fetchone()[0]
    con.close()
    import unicodedata
    typed = "".join(_DIGRAPH_MAP.get(ch, ch) for ch in lat)
    typed = "".join(ch for ch in unicodedata.normalize("NFD", typed)
                    if not unicodedata.combining(ch) and ch.isascii() and ch.isalnum())
    r = client().get("/syriac/search", query_string={"q": typed})
    assert r.status_code == 200
    assert b"Not in the dictionary yet" not in r.data, (lat, typed)


def test_ipa_is_compiled_and_rendered():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    import sqlite3
    con = sqlite3.connect(DB_SYR)
    wid, ipa = con.execute(
        "SELECT word_id, translit_ipa FROM entries WHERE translit_ipa IS NOT "
        "NULL ORDER BY freq DESC LIMIT 1").fetchone()
    con.close()
    r = client().get(f"/syriac/entry/{wid}")
    assert r.status_code == 200
    assert f"/{ipa}/".encode() in r.data, "IPA should render between slashes"
    assert b"draft" in r.data, "IPA must carry a draft badge (unvetted table)"


def test_english_word_miss_wires_the_translations_panel():
    if not DB_SYR.exists():
        print("  (skipped: build the Syriac store first)")
        return
    # An English word with no compiled match must land on the miss page
    # with the online panel armed with that word (English mode), not a
    # silent empty panel. No network here — only the data-query wiring.
    r = client().get("/syriac/search",
                     query_string={"q": "zzqx unmatchable"})
    assert r.status_code == 200
    assert b'data-query="zzqx unmatchable"' in r.data


def test_entry_online_query_uses_the_lemma():
    if not DB_AR.exists():
        print("  (skipped: build the Arabic store first)")
        return
    import sqlite3
    con = sqlite3.connect(DB_AR)
    con.row_factory = sqlite3.Row
    # An inflected form whose lemma differs (e.g. an article-carrying
    # surface form): the online panel must query by LEMMA, because
    # Wiktionary titles pages by citation form.
    row = con.execute(
        "SELECT word_id, lemma FROM entries WHERE lemma IS NOT NULL AND "
        "lemma != '' AND lemma != headword_bare AND is_lexical_form = 0 "
        "ORDER BY freq DESC LIMIT 1").fetchone()
    con.close()
    if row is None:
        print("  (skipped: no inflected form with distinct lemma)")
        return
    r = client().get(f"/arabic/entry/{row['word_id']}")
    assert r.status_code == 200
    assert f'data-query="{row["lemma"]}"'.encode() in r.data


def test_every_keyboard_letter_is_attested_in_its_store():
    if not (DB_SYR.exists() and DB_AR.exists()):
        print("  (skipped: build both stores first)")
        return
    import sqlite3
    # A key that can never match anything is a trap (the old Arabic range
    # leaked U+063B–063F, Khowar/Farsi-orthography letters — a user tapped
    # ػ and got nothing, ever). Every letter offered must occur in at
    # least one stored surface.
    c = client()
    for slug, db in (("syriac", DB_SYR), ("arabic", DB_AR)):
        chars = set()
        con = sqlite3.connect(db)
        for (s,) in con.execute("SELECT DISTINCT surface FROM surface_index"):
            chars.update(s)
        con.close()
        kb = c.get(f"/{slug}/keyboard.json").get_json()
        ghosts = [k for k in kb["letters"] if k["c"] not in chars]
        assert not ghosts, (slug, [(k["c"], k["n"]) for k in ghosts])
    # Points rows: Arabic harakat must be attested in the store's vocalised
    # surfaces. Syriac vowel points can't be attested in a sandbox store
    # (fetch-vocalised is Ameen's-machine-only), so they're pinned to the
    # EAST Syriac sign inventory instead — Western ABOVE/BELOW vowel signs
    # and liturgical marks must not reappear (DECISIONS №40).
    import unicodedata
    ar_chars = set()
    con = sqlite3.connect(DB_AR)
    for (s,) in con.execute("SELECT headword_eastern FROM entries "
                            "WHERE headword_eastern IS NOT NULL"):
        ar_chars.update(s)
    con.close()
    kb = c.get("/arabic/keyboard.json").get_json()
    ghost_pts = [k for k in kb["points"] if k["c"] not in ar_chars]
    assert not ghost_pts, [(k["c"], k["n"]) for k in ghost_pts]
    kb = c.get("/syriac/keyboard.json").get_json()
    east_ok = ("DOTTED", "ZLAMA", "RWAHA", "FEMININE", "QUSHSHAYA",
               "RUKKAKHA", "DIAERESIS")
    for k in kb["points"]:
        name = unicodedata.name(k["c"])
        assert any(t in name for t in east_ok), name


def test_pwa_is_gone():
    # The PWA/offline layer was removed (DECISIONS №34): its routes must
    # 404 rather than half-serve, and ui.js must carry the cleanup that
    # unregisters any worker installed by an earlier visit.
    c = client()
    assert c.get("/sw.js").status_code == 404
    assert c.get("/offline").status_code == 404
    assert c.get("/static/manifest.webmanifest").status_code == 404
    ui = (ROOT / "static" / "ui.js").read_text(encoding="utf-8")
    assert "unregister" in ui, "stale service workers must be unregistered"
    assert "serviceWorker.register(" not in ui


def test_unknown_url_is_a_friendly_404():
    r = client().get("/syriac/not-a-route-here")
    assert r.status_code == 404
    assert b"That isn't a page here" in r.data, "default Flask 404 leaked through"


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
    test_browse_lists_entries_and_clamps_bad_pages,
    test_random_redirects_to_a_compiled_entry,
    test_roots_page_renders_for_both_dictionaries,
    test_root_card_renders_graph_data_and_404s_on_unknown_root,
    test_homepage_common_words_skip_function_words,
    test_entry_shows_full_attestations_for_frequent_words,
    test_lemma_page_lists_the_whole_paradigm,
    test_transliteration_search_finds_entries_both_scripts,
    test_transliteration_suggest_offers_latin_hits,
    test_english_digraph_transcription_finds_entries,
    test_english_meaning_search_finds_entries,
    test_translit_query_with_extra_suffix_still_matches,
    test_english_word_miss_wires_the_translations_panel,
    test_entry_online_query_uses_the_lemma,
    test_every_keyboard_letter_is_attested_in_its_store,
    test_ipa_is_compiled_and_rendered,
    test_pwa_is_gone,
    test_unknown_url_is_a_friendly_404,
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
