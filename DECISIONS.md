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
cleanly when offline. assistance.md rule #3 carries a pointer to this entry
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

**30. Browse/Random, grouped misses, and a UI polish pass** *(2026-07-07)* —
Filled the "you can search it but not leaf through it" gap with two new
retrieval-only routes per dictionary: `/<slug>/browse` (paginated SELECT
over `entries`, ORDER BY drawn from a two-key whitelist — frequency or
alphabetical — never from user text) and `/<slug>/random` (`ORDER BY
RANDOM() LIMIT 1`, then a redirect: it can only land on something already
compiled). Neither adds any code path a keystroke could take to a
generator; rule #3 stands. The misses page now GROUPs BY `q_norm` with a
count and last-seen timestamp instead of listing raw rows — "which forms,
how often, how recently" is the shape that sizes the next compile
(relying on SQLite's documented bare-column-with-MAX(ts) semantics for
the freshest as-typed form). Unmatched URLs get a standalone friendly 404
(like `store_missing.html` — no cfg/meta exists outside a blueprint).
UI: the hardcoded surface colours moved into four palette variables
(`--card/--soft/--wash/--warm`), which bought a dark scheme via
`prefers-color-scheme` for free (same manuscript idea inverted; the
rubric lightened for contrast; `.b-pending` pinned to a fixed
light-ground pair so it can't go light-on-light). A print stylesheet
keeps the entry + apparatus and *drops the online-sources panel* — live
unvetted content has no place in a printed record, same ethos as №28.
Tap-keyboard gained a backspace key, and tap-keys now dispatch an
`input` event so the suggest dropdown tracks them; entry pages gained a
copy-headword button (copies the stored Unicode verbatim; ui.js removes
the button where the clipboard API is unavailable); "/" focuses the
search box; skip-link + `:focus-visible` for keyboard users; favicon and
meta description added. `tests/test_app.py` grew 10 → 13 (browse renders
and clamps junk paging, random 302s to a compiled entry, the friendly
404 actually renders); all five suites green (9/6/13/6/10).

**31. Utility-first rework: root tree, calmer pages, function-word-free
highlights** *(2026-07-07)* — Ameen asked for maximum utility and a less
scattered UI, pointing at peshitta.onrender.com, SEDRA, and
arabicstudentsdictionary.com as models. Three moves, all still pure
retrieval (rule #3 untouched — "loosen the restriction" here meant scope
conservatism, not compile/lookup separation):
(a) *Root tree* (`/<slug>/roots`, in the header nav): every compiled
entry hung off its source root, grouped by the source's own `root_id`
rather than by spelling — SEDRA distinguishes homographic roots (324
root records over 305 spellings in the current store), and merging them
would assert an identity the source doesn't. Letter index on top,
anchors per root, and each entry's Grammar→Root now links into its exact
block. The Arabic tree states plainly that 96 of 150 entries (QAC's
particles/pronouns) carry no root in the source, rather than padding.
(b) *Homepage highlights skip function words* — the request named kad,
ger, lā; implemented instead as a POS-category filter
(`app._CONTENT_POS_WHERE`: pos NOT LIKE particle/pronoun/preposition/
conjunction), verified 2026-07-07 against both stores' actual pos
inventories, so no source-language form is typed from memory (rule #1)
and the rule ports to any future store. Filtered words remain fully
searchable and in Browse; this is display-rank only. Also chosen over a
frequency cutoff, which would have hidden content words (ʔalāhā-class
items rank alongside particles).
(c) *Calmer pages*: homepage is now search-first — one-line lede, a
stats strip (entries / roots / lemmas / random, the SEDRA-style
"multiple entry points" pattern), coverage in one muted line, and the
tap-keyboard folded into a collapsed <details>; the entry page moves the
`sedra3_vocalised` code chip out of the headword area into the
Sources & confidence apparatus, which itself becomes a collapsed
<details> — the audit trail is one click away, not competing with the
entry. Nothing was dropped, only re-ranked. test_app.py 13 → 15 (roots
render on both sides with per-root anchors + the honest no-root note;
the POS filter leaves no function word in the top-12 and doesn't empty
it). All five suites green (9/6/15/6/10).

**32. Theme toggle, interactive root cards, reader-voice copy**
*(2026-07-07)* — Second utility pass on Ameen's direction.
(a) *Light/dark toggle* in the header: explicit choice stored in
localStorage as `data-theme` on <html> (a pre-paint inline script stops
the flash), OS preference still honoured when no choice is made — the
dark palette block is therefore duplicated for the media query and the
attribute selector, with a comment binding the two copies together.
(b) *Root cards* (`/<slug>/root/<root_id>`): each root family as an
interactive force graph — central root node, draggable floating bubbles
sized by corpus frequency, click for an info card — modelled on
peshitta.onrender.com's constellation view but *single-language by
design*: that site draws Hebrew/Arabic cognate bubbles; ours would have
to fabricate cognate relations we have no vetted source for (rule #1),
so the bubbles are exactly the store's own entries for that root_id,
embedded as a JSON island from the same SELECT that renders the plain
list below the graph (progressive enhancement: no JS → the list is the
page; prefers-reduced-motion → settles once, no idle drift). Physics is
~200 lines of vanilla JS (`static/rootgraph.js`), no CDN — the graph
works offline like everything else. Roots-tree headings and each
entry's Grammar→Root now link to the family card.
(c) *Copy rewrite for readers*: home/about/miss/misses/browse/
candidates/roots/footer no longer speak compiler ("compiled offline",
"the store", "logged miss", "query time") — same honesty, user voice
("prepared ahead of time…", "your search has been saved", "Words people
looked for"). store_missing.html stays technical on purpose (its
audience is whoever runs the build). Badge legend gets a plain-language
intro on About; build commands moved under "For the project team".
(d) Small utilities: word of the day on the homepage (date-seeded
deterministic pick among content words — same word for everyone all
day, pure retrieval), and a frequency rank on entry pages ("#N most
frequent", one COUNT). test_app.py 15 → 16 (root card renders its data
island + list and 404s an unknown root; three pinned strings updated
with the copy). All five suites green (9/6/16/6/10).

**33. Wider online sources, transliteration search, lemma pages, full
attestations, and offline/PWA** *(2026-07-08)* — Feature pass on Ameen's
direction ("maximum utility"; remove CAL, keep Wiktionary, add a wider
source). Also finished wiring the light/dark toggle described in №32 (the
header button + `data-theme`/localStorage + pre-paint anti-flash script
were completed this session).

*(a) Online sources reworked.* CAL removed: its browse-CGI returned
unversioned HTML that was brittle to parse and covered only the Syriac
side. `online_lookup.py` now runs three JSON, keyless, documented
MediaWiki/Wikibase sources: Wiktionary **exact entry** (action=parse,
both dicts, as before), Wiktionary **related-page search**
(action=query&list=search — a wider net of inflected forms / compound
phrases / mentions, both dicts, exact page de-duplicated out), and
**Wikidata lexemes** (wbsearchentities&type=lexeme, Arabic only — verified
2026-07-07 that Classical Syriac lexemes are still too sparse there to
query). Wikidata results are language-filtered ("Arabic, noun" kept, "New
Persian, …" dropped) so an Arabic-script homograph doesn't leak other
languages. `lookup_online` now returns `sources` as an **ordered list**
(exact entry first, then wider nets) because Flask sorts JSON object keys
and display order is meaningful; `online.js` iterates the list. New
`DictConfig.wikidata_lang_labels`. Parsers are pure and fixture-tested
against real responses refetched 2026-07-07 (`tests/fixtures/wikidata_*`,
`wiktionary_search_*`); the CAL fixture and all CAL code/tests are gone.
`test_online_lookup.py` 10→14, both live smokes (Wiktionary, Wikidata)
pass and skip cleanly offline.

*(b) Transliteration search.* You can now type a word in English letters
("shlama", "deyn", "allah") or Malayalam and reach the entry.
`suriyani/lookup.translit_candidates()` folds scholarly diacritics to a
bare a–z comparison string (NFD, drop combining marks + modifier letters
— exactly the old CAL `_loose()` spirit, a *comparison* normalisation, not
a transliteration claim) and matches the compiler's already-stored
`translit_lat`/`translit_ml` columns; exact ranks over prefix, then by
frequency. This is **not** a new compile/lookup exception (rule #3): it
SELECTs pre-computed columns and mints nothing. Wired into `resolve()`
(`matched_on="translit"`, shown as "matched on its transliteration") as a
fallback after script lookup — a clean no-op for in-script input — and
into `suggest()` so Latin/Malayalam autocompletes too.

*(c) Lemma pages.* `/<slug>/lemma/<lexeme_id>` shows a word's whole
paradigm — citation form + every inflected form the store compiled —
grouped by the source's own `lexeme_id`, never spelling. Entry pages link
to it ("all N forms →") when a lexeme has more than one compiled form.

*(d) Full attestations.* Entries showed only the first attestation; now
each can show every verse the word appears in. Added `attestations_for()`
to both corpora (`suriyani/corpus.py`, `arabiyya/qac.py`), precomputing a
word→verses map once in `__init__` so it's a lookup, not a rescan; both
backbones store it in a new nullable `attestations` JSON column (added to
the shared SCHEMA and to `ENTRY_FIELDS`, so both stores stay
contract-aligned). Capped at 20 rendered verses per entry with the true
total kept ("Show 20 of its 321 occurrences"), so a common particle can't
bloat the store. Same consonantal (Syriac) / vocalised (Arabic) verse
rendering as the single example. Both sandbox stores rebuilt (safe here:
`headword_eastern` is unfetched, so this is not Ameen's data machine — on
his machine a normal `compile.py build` picks the new column up).

*(e) Offline / installable (PWA).* `static/manifest.webmanifest` +
`static/sw.js` (served from the site root via an app route so its scope is
the whole app, with `Service-Worker-Allowed: /`) + a `/offline` fallback.
Cache strategy: cache-first for `/static/`, network-first for pages,
and **never** cache `online.json` (live/unvetted) or `suggest.json`
(per-keystroke) — caching "live and unvetted" content or stale
autocomplete would contradict what those labels promise. Registered from
`ui.js`, pure progressive enhancement.

*(f) Not done, on purpose.* The Estrangela/Eastern/Western script-variant
switch was scoped out: `headword_western` is empty in both stores (0/574,
0/150), and fabricating western pointing would break rule #1. It waits on
a real `fetch-vocalised` run populating that column. `test_app.py` 16→20
(translit search + suggest, lemma paradigm, full attestations, PWA/offline
+ root-scoped worker). All five suites green (9/6/20/6/14).

**34. Whole-NT corpus, denser root families, cleaner surfaces**
*(2026-07-08)* — Ameen's direction: sparse root graphs, "only words from
Matthew/Quran restricts us", messy online panel, apparatus unreadable for
users, drop the offline layer, fix the invisible keyboard.

*(a) Coverage — the licence-clean way first.* The vendored SEDRA
BFBS.TXT has always contained the **whole Peshitta NT**; we were
filtering to Matthew (book 52). `PeshittaBook` now takes
`book_code=None` for all books (verses keyed by book+chapter+verse so
same-numbered verses can't collide), `compile.py build` grew `--book`
(default: whole NT; `--book 52` reproduces the original scope, which is
what the tests pin via assemble_entries' own default), and meta labels
follow the corpus. Sandbox stores rebuilt at `--top 800` (Syriac:
574→**1630 entries**, 324→504 roots, 195 families with ≥3 words, biggest
32) and `--top 600` (Arabic: 150→**600**, 122 roots, biggest family 16).
No new source, no new licence — the same vendored data, unfiltered. One
test updated for data-truth: the skeleton ܕܝܢ now legitimately matches
two SEDRA records ("but; yet" freq 1828, and "judge" freq 2), so
test_core asserts ranked candidates with the frequent one first instead
of a single entry. The Arabic side already covers its whole corpus
(the Qur'an); widening *that* means new vetted sources — flagged for
Dr. Amaldev, not smuggled in.

*(b) Online sources — verified, not wished for.* PanLex's API host no
longer resolves (probed 2026-07-08 — project in maintenance mode) and
ml.wiktionary has zero coverage for our test words (probed: سلام, الله,
كتاب, ܫܠܡܐ all missing) — both rejected on evidence. What *does* widen
results: the en.wiktionary pages we already fetch carry several related
languages' sections (ܫܠܡܐ: Classical Syriac + Assyrian Neo-Aramaic +
Turoyo + Western Neo-Aramaic; سلام: Arabic + Levantine dialects — read
off the saved fixtures). The exact-entry parser now returns one result
per relevant section — own language first, relatives admitted by a
per-dict regex (`Aramaic$|^Turoyo$` / `Arabic$`), each labelled with its
section name so a Turoyo gloss can never pass as Classical Syriac;
Persian/Urdu/Ottoman sections of the same spelling stay excluded. One
request, ~4× the results. test_online_lookup 14→15.

*(c) UI.* Roots page redesigned from a full listing to a scannable
letter-grouped **chip grid** plus a "Biggest families" strip; entries
now live only on the per-root family page. That page's graph is
**two-level** — root at the centre, dictionary forms as outlined hubs,
inflected forms as filled bubbles on their hub (single-form lexemes
collapse to one bubble; the grouped list below mirrors the same data).
"Elsewhere on the web" became per-source accordions — a one-line summary
("4 found" / "nothing found" / "unavailable") with only the first
non-empty source open, items one line each with the language as a chip
and the snippet clipped. The Sources & confidence apparatus now opens
with plain-language cards ("The Malayalam suggestions — drafted
automatically…, a person hasn't reviewed them yet") with the raw
field/provenance table demoted to a nested "Full technical record".
About rewritten in user voice with licences folded into a collapsible
credits block (the SEDRA acknowledgment stays on every page's footer,
where the licence wants it).

*(d) Fixes/removals.* The invisible on-screen keyboard in light mode was
`color-scheme: light dark` (meta) letting an OS-dark browser paint UA
button text white on our light `--card`; `color-scheme` is now set per
effective theme in CSS and `.key` carries an explicit color. The
PWA/offline layer (№33e) was removed at Ameen's request — routes 404,
and ui.js now *unregisters* any worker a previous visit installed so
nobody is stuck on stale caches. test_app 21/21 (PWA test inverted into
a removal-regression test). All five suites green (9/6/21/6/15).

**35. Keyman OSK suppressed, featured family graph, collapsible online
results, entry action pills, gold accent** *(2026-07-08)* — Bug-fix +
polish round on Ameen's reports.
(a) *The "overlay on the left" and the "invisible keyboard in light
mode" were one culprit*: KeymanWeb's floating on-screen keyboard, which
pops over the page whenever the attached Syriac search box gets focus
and carries its own off-theme styling. We only ever wanted Keyman's
hardware-key mapping (physical keys → Syriac); on-screen input is our
own tap-keyboard's job. The OSK is now hidden by API on init and
re-hidden on focus (keyboard.js), with a CSS kill rule
(`.kmw-osk-frame … display:none !important`) as the guarantee. Our own
keys additionally got `appearance:none` and the `color-scheme` meta was
dropped (the CSS property, set per effective theme since №34, is the
single source of truth) — so no UA button theming can ever paint them
white-on-white again.
(b) *Interactive bubbles back in the root section*: the per-root family
graphs never left, but they were a click deep and read as removed. The
roots index now embeds the biggest family as a **live featured graph**
above the chip grid (same `_family()` helper feeds the index embed and
the root_card page). Entry pages grew an action row beside Copy
headword: a highlighted **⬡ Root family** pill straight to the graph,
and **All N forms** to the paradigm.
(c) *Elsewhere on the web, de-densified again*: each result inside a
source accordion is now itself a `<details>` — first-hand you see only
the word and which language it's from; the meaning and the outward link
unfold on demand.
(d) *Colour*: a second accent `--gold` (manuscript illumination; light
#a8720a / dark #d9a441) on verse quotes, the word-of-the-day card, and
dictionary-form bubbles; section labels carry a rubric side-bar; the
header sits on a wash gradient; the dictionary toggle's active side is
rubric; cards lift on hover. Still the same two-family manuscript
palette, everything through the theme variables. Roots-page test now
pins the featured graph's presence. All five suites green (9/6/21/6/15).

**36. v1.7 — entry-page root tree, floaty-anchored graph, English-style
typing, draft IPA, calmer home** *(2026-07-08)* — Ameen's fix list.
(a) *Version* bumped to 1.7 (`dict_registry.VERSION`). The Random nav
link went (the homepage stat button covers it); the on-screen keyboard
is now OPEN by default (still collapsible); the Common-words card grid
is COLLAPSED by default behind a toggle; Word of the day stays. The
roots index dropped both the embedded featured graph and the
"Biggest families" strip (№35b reverted on request) — it's a pure chip
grid again, and the graph moved to where it's intuitive:
(b) *Root tree on the entry page*, right after Grammar: "how this word
hangs off its root", with the current word's bubble gold-ringed and its
info card pre-opened. Same `_family()` data as the root-card page.
(c) *Graph motion model replaced*: forces used to run continuously, so
bubbles could visibly wander ("fall down"). Now a short relaxation pass
finds anchor positions once; bubbles merely bob a few pixels around
their anchors (nothing accumulates velocity, so nothing can drift),
dragging re-anchors (a hub drags its whole family via parent-relative
offsets), reduced-motion gets a static settled layout. *Condensing*:
the server merges same-spelled forms into one bubble (linking to the
search page that disambiguates the readings, "N readings share this
spelling") and absorbs the citation form into its hub instead of
drawing a twin bubble — no duplicate nodes, as asked. The list view
keeps every row; only the picture condenses.
(d) *English-style typing*: `_translit_folds()` now yields BOTH the
academic strip (š→s, "slama") and the everyday digraph rendering
(š→sh, ṯ→th, ḵ→kh…, map checked against the stores' actual symbol
inventory), plus a difflib tier (≥0.78, only for queries ≥4 chars) —
so shlama/slama/yeshua/alaha/salam/rahman all resolve. Still pure
retrieval over compiler-written columns.
(e) *Suggestion dropdown bugs*: navigation now happens on pointerdown
(the input's blur handler hides the box after 150 ms, so a slower
click's mouseup landed on nothing — the reported "doesn't open the
entry"); and on pages with the on-screen keyboard the box flows in the
page (`.suggest-inline`) instead of floating over the keys, so you can
tap letters and watch matches at once.
(f) *Draft IPA*: new `tables/translit_ipa.tsv` (DRAFT v0 — UNVETTED,
convention owner unassigned — flagged for Dr. Amaldev; VERIFY notes on
the judgment rows: e-quality, ẓ, spirant ḇ, uw/iy contraction) applied
at compile time by `suriyani/ipa.py` — longest-match engine, no
mappings of its own, and NO IPA at all for a word whose romanization
contains an unlisted symbol (№20: honest gap over wrong guess). New
nullable `translit_ipa` column (SCHEMA + ENTRY_FIELDS, both backbones);
both stores rebuilt — 1630/1630 and 600/600 transliterated entries got
IPA (deyn→/dejn/, fiy→/fiː/, allaḏīna→/allaðiːna/). Shown on entries
as /…/ with the draft badge. test_app 21→23 (English-digraph search
resolves; IPA compiled + rendered with badge). All five suites green
(9/6/23/6/15).

**37. Opt-in Syriac typing, meaning search, suffix-tolerant matching,
graph fullscreen, wider stores** *(2026-07-08)* — Ameen's follow-up list.
(a) *PC keyboard types English by default.* Keyman's hardware remap
(east_syriac_qwerty) no longer auto-attaches — a switch under the
on-screen keyboard turns it on/off, persisted in localStorage (a page
reload gives Keyman a guaranteed-clean attach/detach). Off by default:
the search box understands transliterations and meanings, so English
typing is the more useful resting state.
(b) *Search by meaning*: a new gloss tier ("house" → every entry whose
stored English gloss contains the word, whole-word matches, first-sense
hits ranked above later mentions, then frequency; trailing -s forgiven).
Runs only after script and transliteration lookups found nothing, so
romanized words keep their translit reading. Candidates page now phrases
its heading per match type ("N words meaning 'house'" / "N words spelled
like 'kitabun'" / the readings heading), entry pages say "matched on its
English meaning". Still pure SELECT over compiler-written columns.
(c) *Suffix-tolerant transliteration*: a reverse-prefix tier ("baytun"
when the store has "baytu…") between prefix and fuzzy; and the fuzzy
tier is now first-letter-anchored — without the anchor "baytun" scored
0.83 against ʾāyatun ("ayatun") and surfaced a wrong word as THE match
(№20 territory). Both stores also widened to `--top 1500` (Syriac 2198
entries with Lexical Aids, Arabic 1500) — "house" now finds ٱلدَّار and
ܒܝܬ; a truly absent bare form (baytun) stays an honest miss.
(d) *Graph fullscreen*: entry-page and root-card graphs grew "⛶ Full
screen" (Fullscreen API on the graph+info wrapper; a resize nudge keeps
the layout fitting) and entry pages "Open in its own tab ↗" to the
root-card page. Entries whose word carries NO root in the source
(Arabic function words) now say so in a friendly note instead of
silently omitting the tree — the data gap is real, the silence wasn't.
(e) *Malayalam transliteration*: NOT retuned — the values are exactly
what the DRAFT tables' vetting owners must decide (rule #6; Joju Jacob
for Syriac, unassigned for Arabic). Instead the user-visible roughness
was distilled into pointed TODO items in both tables' headers
(word-final chillu ൻ/ൽ/ർ policy, mater contraction, case-ending vowels,
dagger-alif length) so the vetting session addresses precisely what
users notice. test_app 23→25 (meaning search; suffix-tolerant translit;
one assertion updated for the new candidates wording). All five suites
green (9/6/25/6/15).
