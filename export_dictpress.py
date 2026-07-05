#!/usr/bin/env python3
"""Export a compiled store as a dictpress import CSV.

    python export_dictpress.py                              # Syriac store
    python export_dictpress.py data/dictionary_ar.db \
                               data/dictpress_import_ar.csv # Arabic store

The source language, entry labels and frequency label are read from the
store's own meta, so the same exporter serves both dictionaries — the
swappable-backbone contract extending to the publishing layer.

Why this exists: the blueprint's publishing layer is dictpress (§6.1 step 5,
as used by Olam). This app serves its own Flask frontend for demo speed —
a deliberate interim choice, logged in DECISIONS.md — but nothing in the
store is Flask-shaped. This script proves that by emitting the exact CSV
that `dictpress import --file=...` consumes.

Format verified against the dictpress source tree (docs/import.md, v5
Rust/SQLite era, checked 2026-07-02), not from memory. Eleven columns:

    0 type       '-' main entry, '^' definition of the entry above
    1 initial    first character (dictpress auto-fills if empty)
    2 content    the word / the definition text
    3 language   as configured in dictpress (we use: syriac, english, malayalam)
    4 notes      freeform
    5 tokenizer  empty = use column 6
    6 tokens     space-separated search tokens (we supply the consonantal
                 skeleton — the same surfaces our own lookup indexes)
    7 tags       pipe-separated
    8 phones     pipe-separated pronunciations (we supply the two draft
                 transliterations, clearly labelled in notes)
    9 def-types  parts of speech, on '^' rows only
   10 meta       JSON (quotes doubled by the CSV writer automatically)

Each main row carries provenance JSON in meta, so the honesty trail
survives the export.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "dictionary.db"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "dictpress_import.csv"


def bare_tokens(entry: sqlite3.Row) -> str:
    bare = entry["headword_bare"]
    noseyame = "".join(ch for ch in bare if not unicodedata.combining(ch))
    toks = [bare] if bare == noseyame else [bare, noseyame]
    return " ".join(toks)


def main() -> None:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    meta = dict(con.execute("SELECT key, value FROM meta"))
    lang = meta.get("language", "syriac")
    corpus_label = meta.get("corpus_label", "corpus")
    entries = con.execute("SELECT * FROM entries ORDER BY freq DESC").fetchall()

    n_main = n_def = 0
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        for e in entries:
            headword = e["headword_eastern"] or e["headword_bare"]
            phones = "|".join(p for p in (e["translit_lat"], e["translit_ml"]) if p)
            tags = "|".join(t for t in (
                e["pos"],
                "seyame" if e["has_seyame"] else None,
                "enclitic" if e["is_enclitic"] else None,
                None if e["is_lexical_form"] else "inflected-form",
            ) if t)
            notes = (f"entry #{e['word_id']}; {e['morph_summary'] or e['pos'] or ''}"
                     f"; transliterations are DRAFT v0 (unvetted)").strip("; ")
            row_meta = json.dumps({
                "word_id": e["word_id"],
                "freq": e["freq"],
                "corpus": corpus_label,
                "source_vocalised": e["sedra3_vocalised"],
                "provenance": json.loads(e["provenance"]),
            }, ensure_ascii=False)
            w.writerow(["-", "", headword, lang, notes,
                        "", bare_tokens(e), tags, phones, "", row_meta])
            n_main += 1

            if e["gloss_en"]:
                for sense in e["gloss_en"].split(";"):
                    w.writerow(["^", "", sense.strip(), "english", "",
                                "default:english", "", "", "",
                                e["pos"] or "", ""])
                    n_def += 1
            for g in json.loads(e["gloss_ml"] or "[]"):
                w.writerow(["^", "", g["ml"], "malayalam",
                            f"machine draft via Olam key '{g['english_key']}' — unvalidated",
                            "", "", "machine-draft", "", g.get("pos") or "", ""])
                n_def += 1

    print(f"wrote {OUT}  ({n_main} main entries, {n_def} definition rows)")
    print(f"import with:  ./dictpress import --file={OUT.relative_to(ROOT) if OUT.is_relative_to(ROOT) else OUT}")


if __name__ == "__main__":
    main()
