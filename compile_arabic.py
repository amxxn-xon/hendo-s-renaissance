#!/usr/bin/env python3
"""compile_arabic.py — the Arabic dictionary compile (blueprint §6.1).

The Arabic twin of compile.py, importing the *same* SCHEMA so the two
stores are structurally identical — that is the swappable-backbone
contract doing its job:

    python compile_arabic.py build --top 150   # QAC + camel + drafts → SQLite
    python compile_arabic.py stats

There is deliberately no fetch-vocalised step here. The Syriac side needs
one because SEDRA III's abstract vowels cannot produce the Madnhāyā
display form; QAC's word forms ARE the fully vocalised Uthmani
orthography, so headword_eastern is populated at build time from source
data.

The lookup index gets three kinds of rows per entry:
    bare         consonantal skeleton (what an Arabic keyboard produces)
    bare_folded  the skeleton with hamza-seat letters folded (أإٱ→ا,
                 ؤ→و, ئ→ي) — catches input typed without hamza seats
    eastern      the NFC vocalised form — a pasted fully-pointed word
                 matches exactly, same path the Syriac side uses
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from compile import SCHEMA

ROOT = Path(__file__).resolve().parent
DB_DEFAULT = ROOT / "data" / "dictionary_ar.db"


def cmd_build(args: argparse.Namespace) -> None:
    from arabiyya.backbone import assemble_entries
    from arabiyya.glosses import fold
    from suriyani.backbone import ENTRY_FIELDS

    print(f"Compiling top {args.top} Qur'an word analyses ...")
    entries, stats = assemble_entries(ROOT, args.top)

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(SCHEMA)
    cols = ", ".join(ENTRY_FIELDS)
    marks = ", ".join("?" for _ in ENTRY_FIELDS)
    con.executemany(
        f"INSERT INTO entries ({cols}) VALUES ({marks})",
        [tuple(e[f] for f in ENTRY_FIELDS) for e in entries])

    for e in entries:
        bare = e["headword_bare"]
        con.execute("INSERT INTO surface_index VALUES (?,?,?)",
                    (bare, e["word_id"], "bare"))
        folded = fold(bare)
        if folded != bare:
            con.execute("INSERT INTO surface_index VALUES (?,?,?)",
                        (folded, e["word_id"], "bare_folded"))
        eastern = unicodedata.normalize("NFC", e["headword_eastern"])
        con.execute("INSERT INTO surface_index VALUES (?,?,?)",
                    (eastern, e["word_id"], "eastern"))

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top_n": str(args.top),
        "language": "arabic",
        "script": "arabic",
        "corpus": "Qur'an — Quranic Arabic Corpus morphology 0.4 "
                  "(© 2011 Kais Dukes, GNU GPL; text: Tanzil Uthmani "
                  "v1.0.2, CC BY-ND 3.0) — corpus.quran.com",
        "corpus_label": "the Qur'an",
        "dict_label": "Arabic → Malayalam",
        "sources_label": "the Quranic Arabic Corpus (with camel_morph glosses)",
        "freq_label": "Qur'an",
        "stats": json.dumps(stats),
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
    con.commit()
    con.close()

    print(f"-> {db}")
    for k, v in stats.items():
        print(f"   {k:>14}: {v}")


def cmd_stats(args: argparse.Namespace) -> None:
    con = sqlite3.connect(args.db)
    for k, v in con.execute("SELECT key, value FROM meta"):
        print(f"{k}: {v}")
    n, ne, nm = con.execute(
        "SELECT COUNT(*), COUNT(headword_eastern), "
        "(SELECT COUNT(*) FROM misses) FROM entries").fetchone()
    print(f"entries: {n}   with vocalised headword: {ne}   logged misses: {nm}")
    con.close()


def main() -> None:
    from suriyani import make_stdout_utf8_safe
    make_stdout_utf8_safe()  # so stats output survives a redirect on Windows
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compile the Arabic dictionary store from QAC")
    b.add_argument("--top", type=int, default=150,
                   help="how many top-frequency Qur'an word analyses to compile")
    b.add_argument("--db", default=str(DB_DEFAULT))
    b.set_defaults(fn=cmd_build)

    s = sub.add_parser("stats", help="show what is in the store")
    s.add_argument("--db", default=str(DB_DEFAULT))
    s.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
