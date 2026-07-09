# Suriyani–Malayalam Dictionary — Version 1.0

A locally-hosted East Syriac (Madnhāyā) → Malayalam dictionary, compiled
automatically from real sources and served through a small Flask app. Built
as Version 1.0 of *Automating Dictionary Compilation* (Hendo Projects);
the pipeline follows §6.1 of the project blueprint, the entry shape
follows §6.4, and the whole thing is designed so that the Syriac backbone
can be swapped for an Arabic one later without touching the app — which
the Arabic port (`arabiyya/`, see ARABIC_PORT.md) has since proven.

## Quick start

```bash
pip install -r requirements.txt                       # runtime: flask, requests, gunicorn
pip install -r requirements-compile.txt               # compile-only: pymupdf (PDF parsing)
python3 compile.py build --top 100000  # SEDRA III + whole Peshitta NT, every word
                                        #   form (+ Lexical Aids boost, on by default)
                                        #   → data/dictionary.db; --book 52 = Matthew only
python3 compile_arabic.py build --top 100000   # QAC + camel, every word form of the
                                        #   Qur'an → data/dictionary_ar.db
python3 app.py                         # → http://127.0.0.1:5000 — both dictionaries,
                                        #   /syriac/ and /arabic/, toggle in the header
python3 tests/test_core.py             # 9 checks, all doc-anchored
python3 tests/test_arabic.py           # 6 checks, data-anchored
python3 tests/test_lexical_aids.py     # 6 checks, data-anchored
python3 tests/test_app.py              # 28 checks, unified-app (routes, roots, root cards,
                                        #   translit + English + meaning search, lemma
                                        #   pages, attestations, draft IPA, translations)
python3 tests/test_online_lookup.py    # 20 checks, fixture-anchored (2 live, skip offline)
```

One further command matters, and it must run on a normal home/campus
connection (the build environment could not reach the API — its server
refuses automated fetchers):

```bash
python3 compile.py fetch-vocalised     # SEDRA IV API → vocalised Madnhāyā headwords
```

Until that runs, entries show their consonantal headword with an explicit
*“Madnhāyā vocalisation pending”* badge. Every response is cached under
`data/cache/sedra_api/`, requests are spaced 1.5 s apart, and each fetched
record is only accepted after an alignment check (the API record's
consonantal skeleton must equal ours). Add `--inspect` on the first run to
print one raw response and confirm the field layout.

## The two machines

**Compilation** (`compile.py`) is offline, slow-is-fine, and reproducible:
it reads the SEDRA III database files, counts word-record frequencies over
Matthew in the BFBS Peshitta text, and for the top-N records assembles a
full entry — headword, lemma, root, part of speech, bit-decoded morphology,
English glosses, machine-drafted Malayalam gloss candidates, rule-table
transliterations, and the word's first attestation in Matthew as a cited
example. Everything lands in SQLite with per-field provenance and
confidence labels. By default it also widens past Matthew's own top-N cutoff
using *Lexical Aids to the Syriac New Testament*'s whole-NT frequency
ranking as a prioritization signal (never as a text source — see
`suriyani/lexical_aids.py` and `data/lexical_aids/PROVENANCE.md`); disable
with `compile.py build --no-lexical-aids`.

**Lookup** (`app.py`) is online and can only retrieve. It normalises the
query (NFC, script-appropriate characters only, consonantal skeleton),
resolves it against the store, and renders. One match → the entry. Several
word records sharing a skeleton → ranked candidates (try ܐܡܪ: three
morphological readings). Nothing → an honest miss with near matches from
the store, and the query is logged in `misses` so the next compile knows
what people wanted. A live "closest headword" suggest dropdown (also a
plain SELECT against the compiled store — see `suriyani/lookup.py::suggest()`)
surfaces candidates as you type. There is no code path from a user's
keystroke to SEDRA, QAC, CAMeL, Olam, or any generator — if it wasn't
compiled, it isn't shown. One process serves both dictionaries, at
`/syriac/` and `/arabic/`, with a toggle in the header.

One deliberate exception (DECISIONS.md №28): every result page also
carries a clearly-separated **Online sources** panel that fetches live —
after the page has rendered, via `/​<slug>​/online.json`, a route that
never touches the database — from the Comprehensive Aramaic Lexicon
(Syriac side) and Wiktionary (both sides). Its results are transient,
verbatim, always linked to the live source, labelled unvetted, and never
stored; if those sites are down, the compiled page above is unaffected.

## What an entry really contains

Each §6.4 field carries two labels rendered as badges in the UI and kept
in the dictpress export: *where it came from* (provenance) and *how much to
trust it* (confidence). The honest states in this build:

| field | state |
| --- | --- |
| consonantal headword, lemma, root, POS, English glosses, example | **source** — read faithfully from SEDRA III |
| morphology | **decoded** — documented bitfields (SEDRA3.DOC), the doc's own worked example is a unit test |
| vocalised Madnhāyā / Serṭā headwords | **pending** until `fetch-vocalised` runs; never synthesized (see DECISIONS.md №3) |
| Latin & Malayalam transliterations | **draft_unvetted** — deterministic rule tables in `tables/`, to be vetted against Joju Jacob's slides |
| Malayalam glosses | **machine_draft** — Olam pivot, each candidate tagged with the exact English key that matched |

The example sentences are real verses (first attestation in Matthew),
rendered consonantally and cited as such.

## Data sources

* **SEDRA III** (George A. Kiraz) — the complete flat-file database is
  vendored under `data/sedra3/` together with its own format documentation
  and licence, obtained via the `peshitta/sedrajs` repository. This
  supplies the lexicon, morphology, English glosses, and — through
  `BFBS.TXT` — the entire Peshitta NT as word-record pointers, which gives
  us frequency counting and a concordance with SEDRA's own segmentation.
* **SEDRA IV API** (Beth Mardutho) — vocalised Unicode headwords, fetched
  by you (see above).
* **Olam** (olam.in, ODbL) — 216,918-row English→Malayalam dataset used as
  the gloss-drafting pivot; see `data/olam/PROVENANCE.md`, including why
  the official dump is the preferred long-term source.
* **Lexical Aids to the Syriac New Testament** (Kiraz & Lee, 3rd ed.,
  Gorgias Press 2024) — a proprietary source, unlike everything else
  above; used only as a prioritization signal (which additional SEDRA
  word-records are common across the whole NT), never as a text source.
  See `data/lexical_aids/PROVENANCE.md` for the licensing/authorization
  status (flagged for Dr. Amaldev) and DECISIONS.md №27.
* **KeymanWeb** — the `east_syriac_qwerty` keyboard loads from Keyman's
  CDN when reachable (engine pinned per keyman.com docs). Independently of
  it, the page always renders a built-in reference keyboard whose key set
  and labels are generated from Python's Unicode database at startup — an
  alphabet-order grid, not a typing-layout claim.
* **East Syriac Adiabene** font — drop the `.otf` into `static/fonts/`
  (not redistributed here); the CSS falls back to Noto Sans Syriac Eastern.

## dictpress

The blueprint's publishing layer is dictpress; serving Flask now is a
deliberate interim choice (DECISIONS.md №1). `python3 export_dictpress.py`
writes `data/dictpress_import.csv` in the 11-column format verified
against dictpress's own `docs/…/import.md` — main rows in `syriac` with
consonantal search tokens and both transliterations as labelled phones,
definition rows in `english` and `malayalam`, provenance JSON in the meta
column.

## Hosting on Render

An always-on Python host with a writable disk fits this app better than a
serverless platform: it writes to the `misses` table, makes outbound calls
that can take several seconds (Wiktionary/Wikidata), and is a long-running
Flask server by design. `render.yaml` is a ready blueprint.

1. **Keep the proprietary PDF out of the repo.** `data/lexical_aids/*.pdf`
   is git-ignored (Gorgias Press, all rights reserved — DECISIONS №27); it
   is compile-time only, so the deploy never needs it. Everything derived
   from it is already inside `data/dictionary.db`, which *is* committed.
2. Push the repo to GitHub (private is fine; if public, the `.gitignore`
   already keeps the PDF out).
3. On Render: **New → Blueprint**, point at the repo. `render.yaml` defines
   a free web service that installs `requirements.txt` (runtime deps only —
   no heavy `pymupdf`) and starts `gunicorn app:app`. Under gunicorn the
   Werkzeug debugger is never active, so `debug` is off in production
   regardless.

Two honest limitations on the **free** plan, neither of which breaks the
dictionary itself:
- The instance sleeps when idle, so the first hit after a lull takes ~30s
  to wake.
- Its filesystem resets on each deploy/wake, so logged misses don't persist
  long-term (they still work within a running instance; the write is
  best-effort and never 500s — DECISIONS №29). For durable misses, use a
  paid instance with a persistent disk mounted at `data/`, or an external
  database.

To refresh what's served, rebuild the stores locally (`compile.py build`,
optionally `fetch-vocalised` first for vocalised headwords) and commit the
updated `data/*.db`.

## The Arabic port (built)

`suriyani/backbone.py` was the seam, and the port now exists to prove it:
`arabiyya/` produces the same entry keys from the Qur'anic Arabic Corpus
(tier 1) with camel_morph MSA glosses, and the store schema, lookup, app,
Olam pivot, rule-table engine and exporter carried over — the Syriac
tests never broke. Read **ARABIC_PORT.md** for commands, slot mapping,
asymmetries (no fetch step: QAC's forms are already the vocalised
orthography) and honest gaps. Quick taste:

```
python3 compile_arabic.py build --top 150
python3 app.py                   # http://127.0.0.1:5000/arabic/
python3 tests/test_arabic.py
```

## File map

```
compile.py            offline machine (Syriac): build | fetch-vocalised | stats
compile_arabic.py     offline machine (Arabic): build | stats — no fetch step
app.py                online machine: both dictionaries, one process (:5000),
                      /syriac/ and /arabic/ blueprints + header toggle
dict_registry.py      per-dictionary config: db path, script, keyboard builder
export_dictpress.py   store → dictpress CSV (language read from store meta)
suriyani/
  sedra3.py           faithful SEDRA III reading (mapping, parsers, bitfields)
  corpus.py           BFBS Matthew: frequency, verses, first attestations
  translit.py         rule-table engine (tables/ are the editable artifacts)
  olam.py             Olam index + pivot heuristic
  backbone.py         the adapter — §6.4 records; the port contract
  sedra_api.py        SEDRA IV client: cache-first, rate-limited, verified
  lookup.py           normalisation + resolution (retrieval only; script
                      read from each store's meta)
  lexical_aids.py     Lexical Aids coverage boost — prioritization signal
                      only, matched onto SEDRA's own verbatim forms
arabiyya/
  buckwalter.py       QAC extended Buckwalter ↔ Unicode, name-asserted
  qac.py              the Qur'an as corpus: words, morphology, attestations
  glosses.py          camel_morph gloss matching (exact/folded, gated)
  translit_ar.py      Arabic translit engine over the shared RuleTable
  backbone.py         the Arabic adapter — same ENTRY_FIELDS, asserted
tables/               translit_{syr,ara}_{lat,ml}.tsv  (all DRAFT v0)
tools/                extract_camel_glosses.py (reproducible distillation)
data/sedra3/          vendored SEDRA III + SEDRA3.DOC + licence
data/qac/             vendored QAC morphology 0.4 (verbatim) + PROVENANCE
data/camel/           camel-msa-glosses.tsv (MIT) + PROVENANCE
data/olam/            olam-enml.tsv + PROVENANCE.md
data/lexical_aids/    Lexical Aids PDF (proprietary — see PROVENANCE.md)
data/cache/sedra_api/ API response cache (filled by fetch-vocalised)
data/dictionary.db    the compiled Syriac store
data/dictionary_ar.db the compiled Arabic store
tests/                test_core.py (9) + test_arabic.py (6) + test_lexical_aids.py (6)
```

## Licences

* **SEDRA III**: © 1996 George A. Kiraz; free for personal and academic
  use; publications must carry: *“This work makes use of the Syriac
  Electronic Data Retrieval Archive (SEDRA) by George A. Kiraz, distributed
  by the Syriac Computing Institute.”* Whether a derived, redistributed
  database (this SQLite file, the dictpress CSV) is compatible with the
  “no altered versions” clause is an open question flagged for
  Dr. Amaldev — see DECISIONS.md №2.
* **Olam data**: ODbL 1.0 — attribution kept in the app footer and
  `data/olam/PROVENANCE.md`.
* **sedrajs** (packaging through which SEDRA III was obtained): MIT for
  the wrapper code; the data files carry Kiraz's terms above.
* **KeymanWeb**: MIT.
* **Qur'anic Arabic Corpus 0.4**: GNU GPL © 2011 Kais Dukes; underlying
  text Tanzil Uthmani v1.0.2, CC BY-ND 3.0 — both notices vendored
  verbatim in `data/qac/`, obligations mapped in its PROVENANCE.md.
* **camel_morph MSA v1.0**: MIT © 2018–2022 NYU Abu Dhabi (chosen over
  calima-msa on the redistribution axis — DECISIONS №18).
* **Lexical Aids to the Syriac New Testament** (Kiraz & Lee, 3rd ed.,
  Gorgias Press 2024): © 2024 Gorgias Press LLC, all rights reserved —
  the only non-permissive source vendored here. Used under a stated
  IIT Goa/Gorgias Press partnership (attested by Ameen, 2026-07-05);
  **written agreement flagged for Dr. Amaldev to attach** — see
  `data/lexical_aids/PROVENANCE.md` and DECISIONS.md №27. Its own text
  is never stored or redistributed; it is used only to prioritize which
  already-licensed SEDRA III word-records to compile.
* **This repository's code**: licence to be chosen with Dr. Amaldev
  (GPL-compatibility of the eventual Arabic backbone's Qur'anic corpus
  tier makes GPL the likely umbrella — blueprint licensing note).

## Known gaps, by design

The Madnhāyā vocalisation awaits your `fetch-vocalised` run. The
transliteration tables await Joju Jacob's conventions — expect wholesale
value changes there (the machinery won't change). Matres lectionis are not
contracted and linea occultans is not applied in the v0 tables; both are
flagged on every affected entry. The zlama pšiqa/qašya split cannot be
recovered from SEDRA III's five-vowel scheme at all — it arrives only with
the SEDRA IV fetch. Misses persist across rebuilds on purpose: they are
the feedback channel into the next compile.

On the Arabic side: gloss coverage is deliberately conservative (73/150 —
no gloss beats a wrong gloss, DECISIONS №20), and the two Arabic
transliteration tables are DRAFT v0 with no vetting convention assigned
yet (DECISIONS №24). Details in ARABIC_PORT.md.
