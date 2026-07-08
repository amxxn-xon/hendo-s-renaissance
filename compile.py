#!/usr/bin/env python3
"""compile.py — the offline compilation machine (blueprint §6.1).

Everything expensive, fallible, or judgement-laden happens here, once,
before anyone searches anything:

    python compile.py build --top 150      # SEDRA III + corpus + drafts → SQLite
    python compile.py fetch-vocalised      # SEDRA IV API → eastern/western forms
    python compile.py stats                # what's in the store right now

The lookup app (app.py) only ever reads the SQLite file this produces.
It cannot generate content, call APIs, or transliterate — that separation
is the project's core integrity guarantee: nothing reaches a user that
was not compiled, reviewed-or-flagged, and stored beforehand.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_DEFAULT = ROOT / "data" / "dictionary.db"
CACHE_DIR = ROOT / "data" / "cache" / "sedra_api"

SCHEMA = """
DROP TABLE IF EXISTS entries;
DROP TABLE IF EXISTS surface_index;
DROP TABLE IF EXISTS meta;
CREATE TABLE entries (
    word_id            INTEGER PRIMARY KEY,
    headword_eastern   TEXT,
    headword_western   TEXT,
    headword_bare      TEXT NOT NULL,
    sedra3_vocalised   TEXT NOT NULL,
    lemma              TEXT,
    lexeme_id          INTEGER,
    root               TEXT,
    root_id            INTEGER,
    pos                TEXT,
    morphology         TEXT NOT NULL,
    morph_summary      TEXT,
    is_lexical_form    INTEGER NOT NULL,
    has_seyame         INTEGER NOT NULL,
    is_enclitic        INTEGER NOT NULL,
    translit_lat       TEXT,
    translit_ml        TEXT,
    translit_ipa       TEXT,
    translit_flags     TEXT NOT NULL,
    gloss_en           TEXT,
    gloss_ml           TEXT NOT NULL,
    freq               INTEGER NOT NULL,
    example_ref        TEXT,
    example_text       TEXT,
    example_hl         TEXT,
    attestations       TEXT,
    lemma_link_word_id INTEGER,
    provenance         TEXT NOT NULL,
    confidence         TEXT NOT NULL
);
CREATE TABLE surface_index (
    surface TEXT NOT NULL,
    word_id INTEGER NOT NULL,
    kind    TEXT NOT NULL          -- 'bare' | 'bare_noseyame' | 'eastern'
);
CREATE INDEX idx_surface ON surface_index(surface);
CREATE TABLE IF NOT EXISTS misses (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    q      TEXT NOT NULL,
    q_norm TEXT NOT NULL,
    ts     TEXT NOT NULL
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def cmd_build(args: argparse.Namespace) -> None:
    from suriyani.backbone import ENTRY_FIELDS, assemble_entries
    from suriyani.sedra3 import BOOK_NAMES
    from suriyani.sedra_api import SEYAME

    book = None if args.book == "all" else int(args.book)
    corpus_name = ("the whole Peshitta NT" if book is None
                   else BOOK_NAMES.get(book, f"book {book}"))
    print(f"Compiling top {args.top} word records of {corpus_name} ...")
    entries, stats = assemble_entries(ROOT, args.top,
                                      use_lexical_aids=not args.no_lexical_aids,
                                      book=book)
    if not args.no_lexical_aids and stats.get("lexical_aids_parsed"):
        print(f"  Lexical Aids to the Syriac NT: parsed {stats['lexical_aids_parsed']}, "
              f"corrupted {stats['lexical_aids_corrupted']}, "
              f"matched {stats['lexical_aids_matched_words']}, "
              f"unmatched {stats['lexical_aids_unmatched']}, "
              f"added {stats['lexical_aids_added']} new entries beyond top {args.top}")

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    cols = ", ".join(ENTRY_FIELDS)
    marks = ", ".join("?" for _ in ENTRY_FIELDS)
    con.executemany(
        f"INSERT INTO entries ({cols}) VALUES ({marks})",
        [tuple(e[f] for f in ENTRY_FIELDS) for e in entries])

    # The lookup index. 'bare' is what a user pastes from a consonantal
    # text; the seyame-stripped variant catches input typed without the
    # two-dot mark. 'eastern' rows are added later by fetch-vocalised.
    for e in entries:
        bare = e["headword_bare"]
        con.execute("INSERT INTO surface_index VALUES (?,?,?)",
                    (bare, e["word_id"], "bare"))
        noseyame = bare.replace(SEYAME, "")
        if noseyame != bare:
            con.execute("INSERT INTO surface_index VALUES (?,?,?)",
                        (noseyame, e["word_id"], "bare_noseyame"))

    if book is None:
        corpus_meta = "Peshitta NT (BFBS) via SEDRA III — all books"
        corpus_label = "the Peshitta NT"
        freq_label = "NT"
    else:
        corpus_meta = f"Peshitta NT (BFBS) via SEDRA III — {corpus_name} (book {book})"
        corpus_label = f"{corpus_name} (Peshitta NT)"
        freq_label = "Mt" if book == 52 else corpus_name[:3]
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top_n": str(args.top),
        "language": "syriac",
        "script": "syriac",
        "corpus": corpus_meta,
        "corpus_label": corpus_label,
        "dict_label": "East Syriac → Malayalam",
        "sources_label": "SEDRA III and the Peshitta",
        "freq_label": freq_label,
        "stats": json.dumps(stats),
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.close()

    print(f"-> {db}")
    for k, v in stats.items():
        print(f"   {k:>14}: {v}")


def cmd_fetch(args: argparse.Namespace) -> None:
    from suriyani.sedra_api import enrich_db

    report = enrich_db(Path(args.db), CACHE_DIR, limit=args.limit,
                       delay=args.delay, inspect=args.inspect)
    print(f"tried {report['tried']}, filled eastern for {report['filled']}")
    if report["first_raw"] is not None:
        print("--- first raw API response (--inspect) ---")
        print(json.dumps(report["first_raw"], ensure_ascii=False, indent=2)[:2000])
    for key in ("mismatched", "unparsed", "errors"):
        if report[key]:
            print(f"{key}: {report[key][:10]}"
                  + (" ..." if len(report[key]) > 10 else ""))
    if report["mismatched"]:
        print("NOTE: mismatches mean SEDRA IV ids may not align with "
              "SEDRA III record numbers for those words — nothing was "
              "written for them. Please share this output.")


def cmd_stats(args: argparse.Namespace) -> None:
    con = sqlite3.connect(args.db)
    for k, v in con.execute("SELECT key, value FROM meta"):
        print(f"{k}: {v}")
    n, ne, nm = con.execute(
        "SELECT COUNT(*), COUNT(headword_eastern), "
        "(SELECT COUNT(*) FROM misses) FROM entries").fetchone()
    print(f"entries: {n}   with eastern vocalisation: {ne}   logged misses: {nm}")
    con.close()


def main() -> None:
    from suriyani import make_stdout_utf8_safe
    make_stdout_utf8_safe()  # so stats/--inspect output survives a redirect on Windows
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compile the dictionary store from SEDRA III")
    b.add_argument("--top", type=int, default=150,
                   help="how many top-frequency word records to compile")
    b.add_argument("--book", default="all",
                   help="'all' for the whole Peshitta NT (default), or a "
                        "SEDRA book code (52 = Matthew, the original scope)")
    b.add_argument("--db", default=str(DB_DEFAULT))
    b.add_argument("--no-lexical-aids", action="store_true",
                   help="skip the Lexical Aids to the Syriac NT coverage boost "
                        "(data/lexical_aids/) — Matthew-only top-N, old behavior")
    b.set_defaults(fn=cmd_build)

    f = sub.add_parser("fetch-vocalised",
                       help="fetch eastern/western Unicode from the SEDRA IV API "
                            "(run this on a normal internet connection)")
    f.add_argument("--db", default=str(DB_DEFAULT))
    f.add_argument("--limit", type=int, default=None)
    f.add_argument("--delay", type=float, default=1.5,
                   help="courtesy seconds between uncached API hits")
    f.add_argument("--inspect", action="store_true",
                   help="print the first raw API response for shape verification")
    f.set_defaults(fn=cmd_fetch)

    s = sub.add_parser("stats", help="show what is in the store")
    s.add_argument("--db", default=str(DB_DEFAULT))
    s.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
