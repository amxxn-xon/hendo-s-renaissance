# The Arabic port — Arabic → Malayalam over the same machinery

This is the swappable-backbone contract (README §"Porting to Arabic",
`suriyani/backbone.py` docstring) made real: a second dictionary from a
second source language, sharing the store schema, the lookup, the app,
the Olam pivot, the rule-table engine, and the exporter with the Syriac
side. `test_core.py` still passes 9/9; nothing Syriac changed
behaviour.

## Run it

```
python3 compile_arabic.py build --top 150   # QAC + camel + Olam → data/dictionary_ar.db
python3 compile_arabic.py stats
python3 app.py                              # http://127.0.0.1:5000/arabic/
python3 export_dictpress.py data/dictionary_ar.db data/dictpress_import_ar.csv
python3 tests/test_arabic.py                # 6 checks, data-anchored
```

Both dictionaries are served by the same `app.py` process, at `/syriac/`
and `/arabic/`, with a toggle in the header (`dict_registry.py` holds the
per-dictionary config). There is **no fetch-vocalised step** for Arabic:
QAC's word forms are the fully vocalised Uthmani orthography, so the
vocalised headword, and vocalised example verses, are present at build
time from source data — the asymmetry with the Syriac side, where the
Madnhāyā form waits on the SEDRA IV fetch, is a property of the sources,
and the schema absorbs it without change.

## What sits in which slot

`arabiyya/backbone.py` produces the exact `ENTRY_FIELDS` keys (imported
from `suriyani/backbone.py` and asserted). The Syriac-flavoured names are
slots: `headword_eastern` holds the vocalised Uthmani form;
`sedra3_vocalised` holds the source's own encoding — the extended
Buckwalter string, verbatim; `headword_bare` is the consonantal skeleton
(marks and Qur'anic annotation dropped, wasla folded); lexeme/root ids
are enumerated deterministically because QAC, unlike SEDRA, carries no
record ids — entry identity is the *analysis signature* (written form +
per-segment analysis), so the same spelling under a different reading is
a different entry, feeding the ranked-candidates view exactly as SEDRA's
word records did. `has_seyame` and `is_enclitic` are constant 0.

## The pieces

`arabiyya/buckwalter.py` — the 60-symbol QAC extended-Buckwalter table,
every codepoint asserted against `unicodedata`, proven to cover every
FORM/LEM/ROOT in the file (128,219 segments, zero unmapped). Output is
NFC. `arabiyya/qac.py` — faithful parse of the canonical 0.4 file into
words, segments, decoded morphology (unknown flag codes kept verbatim),
frequency, first attestations, and verse rendering from the corpus's own
forms. `arabiyya/glosses.py` — English glosses cross-matched from the
camel_morph MSA lexicon (MIT) in two mechanical tiers, exact and folded,
with the folded tier gated to content words and proper-noun rows gated to
QAC-tagged proper nouns; confidence is **cross_matched**, per-match
records in provenance. `arabiyya/translit_ar.py` + the two
`tables/translit_ara_*.tsv` — orthographic reading rules in the engine,
conventions in DRAFT v0 tables (see gaps).

## Data and licences

`data/qac/` holds the canonical corpus file **verbatim** with both
copyright blocks intact; `PROVENANCE.md` maps each licence obligation
(unchanged copy, source + link to corpus.quran.com, notice reproduced in
derived works) to how this repo meets it. Annotation: GNU GPL © 2011 Kais
Dukes; underlying text: Tanzil Uthmani v1.0.2, CC BY-ND 3.0. `data/camel/`
holds the lemma→gloss lexicon distilled reproducibly
(`tools/extract_camel_glosses.py`) from camel_morph MSA v1.0, MIT © NYU
Abu Dhabi — chosen over calima-msa precisely on the redistribution axis
(DECISIONS №18).

## Honest gaps

Gloss coverage is 73/150 entries: function words match exactly or not at
all, and MSA proper-noun rows are gated, so misses are honest rather than
wrong (DECISIONS №20). The upgrade path is QAC's own GPL word-by-word
English. Both transliteration tables are DRAFT v0 with **no vetting
reference assigned** — the Kerala-usage anchors and their collisions are
flagged row by row, and naming a convention owner is on Dr. Amaldev's
desk (DECISIONS №24). `is_lexical_form` marks any single-segment word
whose skeleton equals its lemma's, so all three case forms of a noun can
qualify — loose by design, documented in `arabiyya/backbone.py`.

## For Dr. Amaldev

Two items: whether GPL as the repository's umbrella licence (already the
likely choice per the blueprint note) is confirmed now that a GPL corpus
is in the tree; and who owns the Arabic→Malayalam transliteration
convention so the draft tables can graduate.
