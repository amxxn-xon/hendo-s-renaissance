#!/usr/bin/env python3
"""Distil a lemma-gloss lexicon from the camel_morph MSA database.

Input:  camel_morph_msa_v1.0.db (ALMOR text format, MIT, NYU Abu Dhabi)
        from the camel_morph repo, official_releases/lrec-coling2024_release/
Output: data/camel/camel-msa-glosses.tsv  (lex \t pos \t root \t glosses)

Only the ###STEMS### section is read; each stem line's feature string
carries lex:, pos:, root:, gloss: fields. Rows are deduplicated on
(lex, pos, gloss). Rerunning against the same release file reproduces the
TSV byte-for-byte, which is the point: the distillation is auditable.
"""
import re, sys
from pathlib import Path

src = Path(sys.argv[1])
out = Path(sys.argv[2])
rows = set()
in_stems = False
for line in src.open(encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("###"):
        in_stems = line == "###STEMS###"
        continue
    if not in_stems or "\t" not in line:
        continue
    feats = line.split("\t")[2]
    d = dict(kv.split(":", 1) for kv in feats.split() if ":" in kv)
    lex, gloss = d.get("lex"), d.get("gloss")
    if lex and gloss and gloss not in ("NO_ANALYSIS", "NTWS"):
        rows.add((lex, d.get("pos", ""), d.get("root", ""), gloss))
with out.open("w", encoding="utf-8") as fh:
    for r in sorted(rows):
        fh.write("\t".join(r) + "\n")
print(f"{len(rows)} rows -> {out}")
