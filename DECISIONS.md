# DECISIONS.md — interim choices, logged as made

Dates are build-session dates. “Flagged: Amaldev” means the call needs his
sign-off before the prototype graduates.

**1. Flask now, dictpress later** *(2026-07-02)* — The demo serves a small
Flask app instead of dictpress so the lookup logic, provenance badges, and
miss-logging could be shaped freely. Deliberate interim choice, not an
architecture change: `export_dictpress.py` emits the verified import CSV,
so the store is dictpress-ready at any moment.

**2. SEDRA III flat files vendored as the offline backbone** *(2026-07-02)*
— The complete SEDRA III database (via `peshitta/sedrajs`) supplies
lexicon, morphology, glosses, and the BFBS Peshitta NT concordance in one
consistent, offline, reproducible package. Licence: Kiraz's terms permit
academic use with the acknowledgment formula; whether redistributing a
*derived* database (SQLite/CSV) trips the “no altered versions” clause is
unresolved. **Flagged: Amaldev.**

**3. Never synthesize Madnhāyā vocalisation** *(2026-07-02)* — SEDRA III
vocalises in an abstract five-vowel ASCII scheme. East Syriac pointing
distinguishes more than it encodes (zlama pšiqa vs qašya, matres
handling); producing it from the scheme would be fabrication. The
`eastern` field therefore comes only from the SEDRA IV API, or stays
visibly pending. The SEDRA III vocalised ASCII is stored verbatim and
shown, labelled as what it is.

**4. fetch-vocalised runs on Ameen's machine** *(2026-07-02)* — The API
host refuses automated fetchers (robots), so the build environment could
not pre-fill the cache. The client is cache-first, spaces requests 1.5 s,
sends an identifying User-Agent, and — because the JSON layout could not
be verified from here either — *searches* the response for the record and
accepts it only when the API's consonantal skeleton equals ours
(id-alignment check). `--inspect` prints the first raw response.

**5. Morphology decoded from documented bitfields** *(2026-07-02)* —
SEDRA3.DOC specifies the 32-bit layout and supplies a worked example
(557056 → common, singular), which is a unit test. Discovered empirically
and documented in code: the data files put the 32-bit features *before*
the 16-bit attributes, the reverse of the DOC's field description order.

**6. Examples render consonantally** *(2026-07-02)* — Verse text is
reconstructed from WORDS.TXT consonantal strings (an exact 1:1 mapping per
the DOC). Vocalised verse text would require №3's forbidden synthesis.
Every example is cited (book chapter:verse, BFBS via SEDRA III) and the
target token is highlighted by position, not string match.

**7. Frequency counts word records, not spellings** *(2026-07-02)* — BFBS
tokens point at SEDRA's morphologically disambiguated word records, so the
frequency list inherits expert segmentation, and identical spellings with
different analyses stay distinct — which is precisely what feeds the
ranked-candidates view (ܐܡܪ → three readings).

**8. Draft transliteration tables, engine kept dumb** *(2026-07-02)* — The
convention belongs to Joju Jacob's slides; the tables in `tables/` are
labelled DRAFT v0 UNVETTED in their headers, every collision is flagged in
a notes column, and the engine refuses to guess (unmapped token → the
field is stored as NULL with the gap named in provenance). Known v0
artifacts, all flagged per-entry: matres not contracted (yešuwʿ), linea
occultans not applied, spirantisation collapses in Malayalam.

**9. Malayalam glosses only via the Olam pivot** *(2026-07-02)* — Drafting
Malayalam is the AI's legitimate zone, but freehand glossing would be
unauditable. The pivot is exact-match with two light normalisations, and
each candidate records the English key that matched, so review is a
two-second chain check. IndicTrans2 stays a documented hook — the model is
too heavy for this environment and adds nothing reviewable that the pivot
lacks at 150 entries. No hit → empty field, shown as an honest gap.

**10. Olam data via a third-party repackage** *(2026-07-02)* — The
official dump URL sits on olam.in, unreachable from the build sandbox; the
216,918-row table came from a GitHub repackage, spot-checked, extracted to
the official dump's TSV shape so the real file drops in later. ODbL
attribution in footer and PROVENANCE.md. Preferred long-term source:
official dump.

**11. No LLM ranker** *(2026-07-02)* — Per the build brief. Ambiguity is
ranked by Matthew frequency, which is transparent and already good; the
hook for anything smarter is the ORDER BY in `lookup.py`.

**12. Two keyboards, honestly labelled** *(2026-07-03)* — KeymanWeb's
`east_syriac_qwerty@syr` loads from the CDN (engine version pinned from
keyman.com's docs) with an onerror flag; independently, a built-in
reference keyboard always renders, its key set and labels generated from
`unicodedata` at startup so every label is the official character name —
verifiable by construction, and explicitly *not* a typing-layout claim.

**13. ETIMOLGY.TXT skipped for v0** *(2026-07-02)* — Encoding quirks, and
etymology is not a §6.4 field. Root + lemma cover the need.

**14. Data quirks handled narrowly, documented in code** *(2026-07-03)* —
Literal `NULL` cross-references (36 rootless lexemes, 1 lexeme-less word,
229 orphan English meanings) parse to None/skip; exactly one record
(WORDS 2:24690) carries stray vocalisation in its consonantal field —
vowels/diacritics are skipped there; two compound proper names contain
interior spaces — kept.

**15. Misses persist across rebuilds** *(2026-07-03)* — The `misses` table
uses CREATE IF NOT EXISTS while everything else is dropped and rebuilt:
logged user demand should outlive any one compile, because it is the input
that sizes the next one.

**16. dictpress format verified in-tree, against stale memory**
*(2026-07-03)* — The 11-column CSV was checked against
`docs/documentation/docs/import.md` in the current dictpress source.
Worth recording: prior knowledge said dictpress was Go+Postgres; the
repo's own README says v5 is a Rust+SQLite rewrite. The data won over the
memory, which is the habit this whole project runs on.

**17. Canonical QAC 0.4 vendored verbatim; the edited fork rejected**
*(2026-07-04)* — The Arabic backbone reads the original
`quranic-corpus-morphology-0.4.txt` (Kais Dukes 2011), obtained as a
byte-exact vendored copy via q-ran/quran and kept unchanged as its terms
require, both copyright blocks intact (`data/qac/PROVENANCE.md` maps each
obligation to how we meet it). The furqan.co fork (mustafa0x/
quran-morphology) is better-tagged in places but adds an unvetted
editorial layer between us and the citable source; its published
Buckwalter table did serve as the cross-check for ours, which is then
independently pinned to Unicode names — the SEDRA pattern again.

**18. Glosses cross-matched from camel_morph MSA, and only there**
*(2026-07-04)* — QAC 0.4 ships no gloss layer. The hablullah word-by-word
data is CC BY-NC-ND — No-Derivatives kills it for a derived database.
calima-msa carries LDC/SAMA-heritage restrictions (licensing axis already
on record). camel_morph's own LREC-COLING 2024 MSA release is cleanly MIT:
a lemma→gloss lexicon is distilled from it reproducibly
(`tools/extract_camel_glosses.py`). Because an MSA lexicon glossing
Qur'anic lemmas is a weaker chain than SEDRA's own English layer, gloss_en
carries a new confidence value, **cross_matched**, never "source", with
per-match records (which lex, which tier) in provenance. Upgrade path:
QAC's own GPL word-by-word English, fetched by the team from
corpus.quran.com later.

**19. Entry identity is the analysis signature** *(2026-07-04)* — SEDRA
gives words database ids; QAC repeats the analysis inline at every
occurrence. One entry = one (written form, per-segment analysis)
signature; same spelling with a different reading stays a distinct entry,
which is what feeds the ranked-candidates view. word_id / lexeme_id /
root_id are enumerated deterministically over the frequency-ranked slice,
so identical inputs rebuild identical stores. Words with two STEM
segments (486 fused compounds) take the first stem for lemma/root/pos and
carry `compound_stems` in morphology.

**20. No gloss beats a wrong gloss** *(2026-07-04)* — Dediacritised
matching collides catastrophically on short function words (ثُمَّ "then"
would have matched ثَمّ "there"), and camel's 68k proper-noun rows gloss
with transliterations ("Min", "Ans"). So: the folded tier is gated to
content tags (N, PN, ADJ, V); noun_prop/abbrev rows count only when QAC
itself says proper noun; function words match exactly or not at all.
Top-300 coverage moved from 68% poisoned to 48% clean, and the 150-entry
build glosses 73 — every one auditable. The misses are honest and listed
for the WBW upgrade.

**21. Reading rules in the engine, conventions in the tables**
*(2026-07-04)* — The Arabic transliterator applies only rules that are
definitional in the orthography itself: mater folding, diphthongs, tanwin
seats, shadda, madda-alef (mater after a fatha, ʾā standalone), the
otiose alef of ـُوا, and article-lam assimilation (a bare lam after
word-initial wasla before a geminate *is* the absorbed article — this is
why ٱلرَّحْمَٰن correctly yields arraḥmān with no sun-letter table
needed). One target-script orthographic fact also lives in the engine:
Malayalam gemination of r must be chillu-spelled (ർറ), because റ+്+റ
ligates as റ്റ and reads ṯṯa. Everything conventional — which letter
renders ص, whether ay is ൈ — stays in the two DRAFT v0 tables.

**22. Field names are schema slots, not descriptions** *(2026-07-04)* —
The Arabic entries reuse the Syriac-flavoured column names as semantic
slots: `headword_eastern` = vocalised display headword,
`sedra3_vocalised` = the source's own encoding (here: extended
Buckwalter, verbatim), `has_seyame`/`is_enclitic` = constant 0. Renaming
would have forked the schema and everything downstream for cosmetics; the
dictpress export uses neutral labels anyway. The mapping is documented in
`arabiyya/backbone.py`'s docstring and ARABIC_PORT.md.

**23. NFC at the conversion boundary** *(2026-07-04)* — Buckwalter mark
order (shadda before its vowel) is not Unicode canonical order, so raw
conversion output failed substring comparison against NFC input. to_arabic
now returns NFC — a canonical-equivalence operation, not an edit — so
stored forms, rendered pages, and normalised queries all agree byte-wise.

**24. Arabic→Malayalam vetting reference: unassigned — flag for
Dr. Amaldev** *(2026-07-04)* — The Syriac tables have Joju Jacob's
convention to anchor to; the Arabic tables do not yet have an equivalent.
The draft cites spellings common in Kerala usage (സ്വലാത്ത്, റമളാൻ,
ളുഹർ, ഖുർആൻ, ജുമുഅ, the മഅ്ദനി pattern) with VERIFY on every such row,
plus the known collisions (خ/ق→ഖ, ض/ظ→ള, ح/ه→ഹ). Someone must own the
convention before these leave draft.

**25. One lookup, two scripts — the store says which** *(2026-07-04)* —
resolve() reads a `script` key from the store's own meta and picks the
input filter accordingly; the Arabic bare form mirrors
arabiyya.buckwalter.skeleton (annotation signs and tatweel dropped, wasla
folded) without suriyani importing arabiyya. The index gains a
`bare_folded` kind (hamza-seat letters folded) so hamza-less typing still
lands. Syriac behaviour is byte-identical — test_core stayed 9/9
throughout.

**26. One interface, two Blueprints — app_arabic.py retired**
*(2026-07-05)* — Merged the two demo apps (Syriac on :5000, Arabic on
:5001) into a single `app.py` process serving both stores as Flask
Blueprints under `/syriac/` and `/arabic/`, with a header toggle between
them (`dict_registry.py` is the new single source of truth for per-
dictionary config: db path, script, font class, keyboard builder).
`app_arabic.py` — which existed only to rebind `app.py`'s module globals
onto a second port — is deleted; its whole reason to exist is what the
toggle replaces. Explicitly confirmed with Ameen before building: the
richer per-word linguistic info this UI pass adds (promoted provenance
panel, confidence-tier badges, live suggest) stays **compile-time only**
— nothing new reaches `app.py` from a live SEDRA/QAC/CAMeL call at query
time; the compile/lookup separation (§6.1) is unchanged. Added
`suriyani/lookup.py::suggest()` (prefix match over `surface_index`,
falling back to the existing fuzzy `_near_matches`, itself factored out
of `resolve()`'s miss branch) for a live "closest headword" dropdown as
the user types — still a plain SELECT, same integrity guarantee as
`resolve()`, no miss-logging since a partial word mid-typing isn't a real
query. Fixed two latent template bugs surfaced while unifying: Arabic
entries were rendering through the `.syr` font-class/CSS (now
`cfg.font_class`, `"syr"` or `"ar"`), and Arabic's `cross_matched`
gloss_en provenance (a nested dict, not a string — see
`arabiyya/backbone.py`) was never handled by `entry.html`'s provenance
table, which would have printed a raw Python dict repr the first time
anyone opened such an entry.

**27. Lexical Aids to the Syriac NT — a prioritization signal, never a
text source** *(2026-07-05)* — Ameen searched ܫܠܡܐ and got only near
matches: the Syriac store only compiles the top-150 word-records by
*Matthew* frequency, and ܫܠܡܐ's SEDRA record occurs only once there
(46 times across the whole NT — common, just not in that one book;
2,926 of Matthew's 4,533 distinct word-records are hapax legomena, so
this is systemic). Ameen supplied *Lexical Aids to the Syriac New
Testament* (Kiraz & Lee, 3rd ed., Gorgias Press 2024) and said Gorgias
Press has partnered with IIT Goa and approved its use — attested by
Ameen, no written agreement in hand yet, **flagged for Dr. Amaldev** to
attach it (same pattern as №2, №24). This is a fully proprietary
commercial work (no academic carve-out unlike SEDRA III), the first
non-permissive source in the tree — see `data/lexical_aids/PROVENANCE.md`.

Design: `suriyani/lexical_aids.py` never stores or displays a single
character of the book's own text. It parses Chapter 1 (Word Frequency
List — frequency across the *whole* Peshitta NT) with `pymupdf`,
validates every extracted Syriac span against the Syriac Unicode block
character-by-character, and matches clean skeletons back onto **SEDRA
III's own verbatim consonantal forms** — restricted to word-records that
also occur ≥1× in Matthew, so every entry added this way still gets a
genuine first-attestation example, no schema/shape change. A skeleton
that's corrupted, unmatched, or never attested in Matthew is an honest
gap, not guessed. Verified empirically: extraction has real font-encoding
corruption (~9% of Chapter 1's 883 entries — stray Greek glyphs replacing
Syriac letters, e.g. ref 44 "much, many" → `ܣܰΏ݁ܺܝܳܐܐ`); the parser
rejects a truncated Syriac run unless the character immediately following
it is plain ASCII (the plausible start of a category abbreviation) —
otherwise the truncation is corruption, not a word boundary, and the
whole entry is dropped rather than accepted partial.

`suriyani/backbone.py::assemble_entries` merges the matched word-records
in before the existing per-word-record loop (unchanged for every field),
adding one `provenance["_selection"]` note only on entries that would
**not** have made Matthew's own cutoff — caught a real bug here during
review: the first version tagged every book-matched entry regardless,
which put a false "wouldn't have made the cutoff" claim on words (e.g.
ܕܝܢ, word_id 4405) that were already natively in the top-150. Fixed by
tracking which word_ids were actually added by the merge, not just which
ones the book happens to also list. Result on `--top 150`: 424 additional
entries (574 total), 806/883 book entries cleanly parsed, 390 matched to
an attested SEDRA record. Default on (`compile.py build
--no-lexical-aids` to get the old Matthew-only behaviour back exactly).
**ܫܠܡܐ itself is still not covered** — it isn't in this book's Chapter 1
list either; fixing that specific word would need widening the compiled
corpus from Matthew-only to the full Peshitta NT (BFBS.TXT already
covers all books) — a separate, bigger change, deliberately out of scope
here per Ameen's explicit choice this session.

**28. Online sources section — a deliberate, narrow exception to the
compile/lookup separation** *(2026-07-05)* — Ameen asked for a live
"online" section alongside the compiled results, explicitly accepting
the tradeoff rule #3 exists to prevent ("i understand i told u before to
be strict, but we need to maximize utility too"). Scoped to keep the
compiled store's integrity guarantee intact:

*What was built.* `online_lookup.py` + one route per dictionary
(`/<slug>/online.json`) + a client-side panel (`templates/_online.html`,
`static/online.js`) rendered on entry/candidates/miss pages, below the
compiled content, inside a dashed-border box headed by an explicit
disclaimer (live, unreviewed, may be wrong, nothing stored). Sources per
dictionary come from `dict_registry.py`: Syriac queries **CAL** (the
Comprehensive Aramaic Lexicon, cal.huc.edu — keyless public browse CGI,
HTML parsed; interface verified live this session: jump-grid links gave
the ASCII scheme `) b g d h w z x T y k l m n s ( p c q r $ t`, one code
per consonant Alaph→Taw, so `CAL_TRANSLIT` is built by zipping against
the already-verified `sedra3._UNICODE_CONSONANTS` rather than retyping
codepoints) and **Wiktionary** (MediaWiki `action=parse` API, L2 headings
"Classical Syriac"/"Syriac"); Arabic queries Wiktionary only ("Arabic"
heading) — CAL is Aramaic, not Arabic. A live query for ܫܠܡܐ returned
CAL's `šlm, šlmˀ — "wellbeing; peace"` — the exact word whose compiled
miss started this thread of work.

*What keeps it safe.* The route never touches `db()` — structurally
separate code path, `online_lookup.py` never imports sqlite3. Results
are transient (rendered client-side after page load), verbatim from the
source, always linked out; nothing is stored, nothing feeds a compiled
entry's gloss/provenance/confidence, no miss-logging. A slow or down
external site degrades to a per-source "couldn't reach X just now" note;
the compiled page above is already rendered and unaffected. Tests
(`tests/test_online_lookup.py`, 10 checks) run the parsers against saved
verbatim response fixtures (`tests/fixtures/`, fetched 2026-07-05) so
the suite doesn't depend on the network; two live smoke tests skip
cleanly when offline. CLAUDE.md rule #3 carries a pointer to this entry
rather than silently contradicting the code.

*Deferred.* General web search needs a real API key (Google/Bing/Brave/
SerpAPI) — none available yet; no ToS-violating scraper built instead.
LLM-generated content remains excluded entirely (rule #4 untouched).

**29. v1.0 hardening pass — prototype → Version 1.0** *(2026-07-05)* —
Rebranded off "prototype" (a single `VERSION="1.0"` in `dict_registry.py`,
surfaced via a Flask context processor and the online-lookup User-Agent),
and ran a multi-dimensional review whose confirmed findings were fixed:
(a) the live external fetches (`online_lookup.py`) now stream with a 2 MB
cap, pin UTF-8 decoding (CAL's diacritics were otherwise mojibake under a
"verbatim" label), don't follow redirects, bound the world-editable
Wiktionary template-strip, and defend against valid-but-wrong-shape JSON
— so no external response can 500 `/online.json` or pin a worker; (b)
`suriyani/lookup.normalise()` caps cleaned input at 64 chars, bounding the
difflib scan, the logged-miss size, and the forwarded external query at
one choke point; (c) miss-logging is wrapped so a locked/read-only store
can't turn a miss into a 500; (d) a combining-marks-only query (a lone
vowel point) no longer matches every stored surface; (e) an absent
compiled store is a clean 503 with build instructions instead of a 500
that also minted a stray zero-byte db file (data-hygiene); (f) wrong-
script input (Arabic pasted into the Syriac dictionary, romanisation) now
shows an explaining notice instead of a silent redirect; (g) `debug=True`
is gone — the Werkzeug console is opt-in via `DICT_DEBUG=1`, never
default; (h) all CLI/test output is forced UTF-8-safe
(`suriyani.make_stdout_utf8_safe`), fixing the cp1252 crash when
`compile.py stats`/`--inspect` output is redirected on Windows, and the
test runners now report environmental errors instead of aborting the run.
Regression tests added for the load-bearing fixes; all five suites green
(9/6/6/10/10).
