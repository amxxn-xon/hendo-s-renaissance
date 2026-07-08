# assistance.md

Working instructions for AI assistance on this repository. Read before
touching anything. The project blueprint lives in the project knowledge —
cite it by section number (§6.1, §6.4 …); never re-summarise it.

## What this is

"Automating Dictionary Compilation" — Hendo Projects, intern Ameen,
supervisor Dr. Amaldev (IIT Goa). This repo is the working prototype:
two dictionaries over one machinery — East Syriac (Madnhāyā) → Malayalam
and Arabic → Malayalam — compiled offline into SQLite, served by a demo
Flask app, exportable to dictpress for the eventual Olam-style portal.

Scope is deliberate (§4). Current deliverable: the two dictionaries above.
Arabi Malayalam and Suriyani Malayalam as *scripts* are a separate future
port of this workflow (they belong to the Karshon reference document, not
this repo). Do not suggest scope expansions casually.

## Hard rules — these outrank everything else

1. **Never invent source-language text.** No fabricated Syriac, Arabic,
   or Malayalam-claims — not in code, comments, tests, or docs. If a form
   is uncertain, say so and name the verification anchor (Joju Jacob's
   slides, Sokoloff CSD, Payne Smith for Syriac; the vendored corpus data
   for Arabic). Test fixtures must be data-anchored: copied verbatim from
   vendored files, or constructed from them — never typed from memory.

2. **Data beats memory.** Verify file formats, licences, APIs, and
   encodings empirically against the artifact in the tree before coding
   against them (see DECISIONS №16 for why). Encoding maps must be
   verifiable by construction: every codepoint asserted against
   `unicodedata.name` (pattern: `suriyani/sedra3.py`,
   `arabiyya/buckwalter.py`).

3. **Compile/lookup separation (§6.1).** Everything fallible — parsing,
   gloss matching, transliteration, pivoting — happens at compile time,
   once, into the store. `app.py`/`lookup.py` only SELECT. There is no
   code path from a user keystroke to an API, an LLM, or a generator. A
   query that matches nothing is an honest miss, logged.
   *One deliberate, Ameen-approved exception (№28, sources reworked
   №33):* the "Elsewhere on the web" panel (`online_lookup.py`,
   `/<slug>/online.json`) fetches live from Wiktionary (exact entry +
   related-page search, both dictionaries) and Wikidata lexemes (Arabic
   only) — transient, display-only, never stored, never touches the db,
   labelled unvetted in the UI. Transliteration *search*
   (`suriyani/lookup.translit_candidates`) is NOT an exception: it only
   SELECTs the compiler's own stored `translit_lat`/`translit_ml`
   columns, minting nothing. Do not widen the online panel without a new
   DECISIONS entry; LLM generation stays excluded.

4. **AI's role is bounded**: drafting Malayalam glosses and ranking
   candidates. AI never generates source-language forms, transliterations
   (those come from human-editable rule tables), or example sentences
   (those come from the corpus, cited).

5. **Log decisions.** Any non-obvious choice gets a dated, numbered entry
   in `DECISIONS.md` at the moment it is made. No approval gates during
   build phases — Ameen delegates; the log is the accountability.

6. **Drafts stay flagged.** The four `tables/translit_*.tsv` files carry
   `DRAFT v0 — UNVETTED` headers and row-level VERIFY/COLLISION notes.
   These do not come off until a named convention owner vets them
   (Syriac: Joju Jacob's slides; Arabic→ML: owner unassigned — flagged
   for Dr. Amaldev). Entries display draft/confidence flags; keep it so.

7. **Vendored data is verbatim.** `data/qac/` must remain byte-exact
   (its licence forbids modification); `data/sedra3/` likewise per
   Kiraz's terms. All processing happens at read time. Each vendored
   source has a `PROVENANCE.md` mapping licence obligations to how we
   meet them — extend that pattern for any new source.

8. **Licensing axis = redistribution compatibility**, not commercial/
   non-commercial. GPL is the current umbrella floor (QAC is in the
   tree). ND-licensed data cannot feed a derived database (that killed
   hablullah's word-by-word). LDC-heritage databases (calima-msa) are
   out; use camel_morph's own MIT release. First exception: *Lexical
   Aids to the Syriac NT* (Gorgias Press, all rights reserved) is used
   under a stated IIT Goa partnership (flagged for Amaldev to formalize
   — DECISIONS №27) — and even so, its own text is never stored or
   redistributed, only used as a prioritization signal onto data already
   cleared under this axis. That pattern (signal, not text, when a
   source's licence doesn't clear the axis outright) is the template for
   any future non-permissive source.

9. **No gloss beats a wrong gloss** (DECISIONS №20). Prefer honest gaps
   over inflated coverage anywhere a match could be silently wrong.

## Architecture anchors

- **The adapter contract**: `suriyani/backbone.py` defines
  `ENTRY_FIELDS` and the `assemble_entries(repo_root, top_n) ->
  (entries, stats)` shape. Any backbone (see `arabiyya/backbone.py`)
  imports ENTRY_FIELDS and asserts its output keys against it. Field
  names are schema *slots*, not descriptions (№22): `headword_eastern` =
  vocalised display headword; `sedra3_vocalised` = the source's own
  encoding, verbatim.
- **One SCHEMA, two stores**: `compile.py` owns SCHEMA;
  `compile_arabic.py` imports it. Stores self-describe via `meta`
  (`language`, `script`, `corpus_label`, `freq_label`, …); the app,
  lookup, and exporter read labels from meta, never hardcode them.
- **Engines vs tables (№21)**: transliteration engines contain only
  rules definitional in the orthography (maters, shadda, article-lam
  assimilation, chillu gemination for r); every *convention* lives in
  the editable TSVs.
- **Misses persist across rebuilds** (№15) — they size the next compile.

## Commands

```
python3 compile.py build --top 800          # Syriac store — whole Peshitta NT by
                                             #   default (№34); --book 52 for the old
                                             #   Matthew-only scope. Lexical Aids boost
                                             #   on by default — --no-lexical-aids to
                                             #   skip, see DECISIONS №27
python3 compile.py fetch-vocalised          # SEDRA IV → Madnhāyā (Ameen's machine only)
python3 compile_arabic.py build --top 600   # Arabic store (no fetch step — by design)
python3 app.py                              # :5000 — both dictionaries, /syriac/ and
                                             #   /arabic/, toggle in the header
python3 tests/test_core.py                  # must stay 9/9
python3 tests/test_arabic.py                # must stay 6/6
python3 tests/test_app.py                   # unified-app: routes, roots, root cards,
                                             #   translit + English-digraph + meaning
                                             #   search, lemma pages, attestations,
                                             #   draft IPA — 25/25
python3 tests/test_lexical_aids.py          # Lexical Aids coverage boost, must stay 6/6
python3 tests/test_online_lookup.py         # Wiktionary/Wikidata panel, 15/15
                                             #   (2 live tests skip offline)
python3 export_dictpress.py [db] [out.csv]  # language read from store meta
```

Both suites must pass after any change, whichever side you touched.

## Data hygiene

On Ameen's machine, `data/dictionary.db` contains locally fetched
Madnhāyā vocalised forms and `data/cache/` the SEDRA IV responses —
**never overwrite either** when merging updates; ship changed-file lists
instead of whole-tree replacements. Sandbox rebuilds are fine (no fetch
has run there). Templates other than `index.html` may differ from any
one session's context — patch only files fully in view; never regenerate
a file you haven't read this session.

## Working with Ameen

Concise, high-information prose; bullets only when content is genuinely
list-shaped. Push back when a choice would undermine quality — don't
agree to be agreeable. Skip filler caveats.

Python is past-beginner: explain what code does and why, not just what to
paste. Prefer stdlib and well-known packages, type hints, small runnable
snippets over scaffolds. Supervisor-facing text (for Dr. Amaldev) is
stripped to actionable points; use "we/us" when writing for both interns.

Epistemic care on Syriac and Arabic: under-resourced domains where
confident hallucination is the failure mode. Flag uncertainty; name what
would verify a claim; when unsure of a form, say so.

Don't: re-summarise the blueprint; suggest scope expansions; translate or
transcribe Malayalam audio (ask for written summaries); model the LaTeX
running documentation on any reference document.

## LaTeX defaults

XeLaTeX with polyglossia, never pdflatex. Fonts: East Syriac needs an
OpenType face — Beth Mardutho's East Syriac Adiabene or, for Hendo work,
the private EastSyriacMalankara (manual upload to Overleaf); Malayalam
needs its own (Chilanka in current use); Arabic: Amiri. Show the preamble
explicitly whenever a package enters. `longtable` takes its own
`\caption` and must never be nested in a `table` float. Unverified
script blocks go in `\pending{…}` placeholders — Ameen supplies verified
Unicode; never "correct" niche Syriac/Arabi-Malayalam codepoints. For
structure-only compile checks without the target fonts: substitute
locally available faces (e.g. DejaVu), run xelatex twice, check exit
code and log.
