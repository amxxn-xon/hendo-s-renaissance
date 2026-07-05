"""The Syriac backbone adapter: SEDRA III → §6.4 entry records.

THE ADAPTER CONTRACT (read this before porting to Arabic)
---------------------------------------------------------
`assemble_entries(paths, top_n)` returns a list of plain dicts, one per
dictionary entry, with exactly the keys in ENTRY_FIELDS below. compile.py
turns them into SQLite rows and app.py reads only the database — neither
knows anything SEDRA-specific. An Arabic backbone (blueprint: Qur'anic
Arabic Corpus + Camel Morph) is a sibling module producing the same keys:
`headword_bare` becomes the unvocalised Arabic form, `sedra3_vocalised`
has an Arabic analogue or stays None, provenance strings name the Arabic
sources, and the frequency corpus is the Qur'an instead of Matthew.
Nothing outside this module should need to change.

Field-level honesty: every entry carries a per-field `provenance` dict
(where each value came from) and a `confidence` dict (source / decoded /
machine_draft / draft_unvetted / pending). The UI renders these as badges;
they survive into the dictpress export. This is the §6.3 uncertainty
requirement made concrete.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import lexical_aids, sedra3
from .corpus import PeshittaBook
from .olam import OlamIndex, pivot
from .translit import RuleTable, transliterate_latin, transliterate_malayalam

ENTRY_FIELDS = [
    "word_id", "headword_eastern", "headword_western", "headword_bare",
    "sedra3_vocalised", "lemma", "lexeme_id", "root", "root_id", "pos",
    "morphology", "morph_summary", "is_lexical_form", "has_seyame",
    "is_enclitic", "translit_lat", "translit_ml", "translit_flags",
    "gloss_en", "gloss_ml", "freq", "example_ref", "example_text",
    "example_hl", "lemma_link_word_id", "provenance", "confidence",
]

# Constant per-field provenance for this backbone. The eastern/western
# values are overwritten by sedra_api.enrich_db once fetched.
_PROVENANCE = {
    "headword_bare": "SEDRA III WORDS.TXT consonantal; 1:1 Unicode mapping per SEDRA3.DOC",
    "sedra3_vocalised": "SEDRA III WORDS.TXT vocalised field, verbatim (abstract 5-vowel ASCII scheme)",
    "headword_eastern": "pending fetch from SEDRA IV API (run: python compile.py fetch-vocalised)",
    "headword_western": "pending fetch from SEDRA IV API (run: python compile.py fetch-vocalised)",
    "lemma": "SEDRA III LEXEMES.TXT",
    "root": "SEDRA III ROOTS.TXT",
    "pos": "SEDRA III lexeme category bits (SEDRA3.DOC)",
    "morphology": "SEDRA III WORDS.TXT feature bits, decoded per SEDRA3.DOC",
    "gloss_en": "SEDRA III ENGLISH.TXT (glosses derived from Payne Smith)",
    "gloss_ml": "Olam English→Malayalam pivot (ODbL); machine draft, unvalidated",
    "translit_lat": "rule table tables/translit_syr_lat.tsv — DRAFT v0, UNVETTED",
    "translit_ml": "rule table tables/translit_syr_ml.tsv — DRAFT v0, UNVETTED",
    "example": "Peshitta NT (BFBS) via SEDRA III BFBS.TXT; consonantal rendering",
}

_CONFIDENCE = {
    "headword_bare": "source",
    "sedra3_vocalised": "source",
    "headword_eastern": "pending",
    "headword_western": "pending",
    "lemma": "source",
    "root": "source",
    "pos": "source",
    "morphology": "decoded",
    "gloss_en": "source",
    "gloss_ml": "machine_draft",
    "translit_lat": "draft_unvetted",
    "translit_ml": "draft_unvetted",
    "example": "source",
}


#: Vendored under data/lexical_aids/ — see PROVENANCE.md there for the
#: licensing/authorization status and the safety design summarized in
#: suriyani/lexical_aids.py's own module docstring.
_LEXICAL_AIDS_PDF = "lexical-aids-3rd-ed-2024.pdf"


def assemble_entries(repo_root: Path, top_n: int,
                     use_lexical_aids: bool = True) -> tuple[list[dict], dict]:
    """Build entry dicts for the top_n most frequent Matthew word records,
    plus (by default) any additional SEDRA word-records that Lexical Aids
    to the Syriac New Testament's own whole-NT frequency ranking flags as
    common enough to include (see suriyani/lexical_aids.py — this never
    stores that book's own text, only uses it to pick which extra SEDRA
    word-records are worth compiling).

    Returns (entries, stats). Pure function of the files on disk — running
    it twice yields identical output, which is what makes the compile step
    auditable (§6.1: compilation is offline and reproducible).
    """
    d = repo_root / "data" / "sedra3"
    sedra3.unicode_sanity_check()

    roots = sedra3.parse_roots(d / "ROOTS.TXT")
    lexemes = sedra3.parse_lexemes(d / "LEXEMES.TXT")
    words = sedra3.parse_words(d / "WORDS.TXT")
    english = sedra3.parse_english(d / "ENGLISH.TXT")
    matthew = PeshittaBook.load(d / "BFBS.TXT", book_code=52)

    lat_table = RuleTable(repo_root / "tables" / "translit_syr_lat.tsv")
    ml_table = RuleTable(repo_root / "tables" / "translit_syr_ml.tsv")
    olam = OlamIndex(repo_root / "data" / "olam" / "olam-enml.tsv")

    selected = matthew.top(top_n)
    selected_ids = {wid for wid, _ in selected}

    # Only word-records that Matthew's own frequency cutoff would NOT have
    # selected get the "_selection" provenance note below — a word that's
    # in the native top_n anyway wasn't included *because of* Lexical Aids,
    # even if it also happens to appear in that book's list, and the note
    # must not claim otherwise (a wrong provenance claim is exactly what
    # this project's honesty rules forbid).
    added_via_lexical_aids: dict[int, "lexical_aids.LexicalAidEntry"] = {}
    la_stats = {"lexical_aids_parsed": 0, "lexical_aids_corrupted": 0,
                "lexical_aids_matched_words": 0, "lexical_aids_unmatched": 0,
                "lexical_aids_added": 0}
    la_pdf = d.parent / "lexical_aids" / _LEXICAL_AIDS_PDF
    if use_lexical_aids and la_pdf.exists():
        try:
            import fitz  # noqa: F401  (pymupdf) — just probing availability
        except ImportError:
            print("  Lexical Aids: 'pymupdf' not installed for this Python "
                  "interpreter (pip install -r requirements.txt) - skipping "
                  "the coverage boost, Matthew-only top_n this run.")
        else:
            lexical_aids.sanity_check(la_pdf)  # loud on real drift, not swallowed
            la_entries = lexical_aids.parse_word_frequency_list(la_pdf)
            lexical_aid_source, la_match_stats = lexical_aids.match_against_sedra(
                la_entries, words, matthew)
            la_stats.update({f"lexical_aids_{k}": v for k, v in la_match_stats.items()
                            if k != "parsed"})
            la_stats["lexical_aids_parsed"] = la_match_stats["parsed"]
            for wid, la_entry in lexical_aid_source.items():
                if wid not in selected_ids:
                    selected.append((wid, matthew.freq[wid]))
                    selected_ids.add(wid)
                    added_via_lexical_aids[wid] = la_entry
                    la_stats["lexical_aids_added"] += 1

    # citation-form links: lexeme_id -> compiled word_id of its lexical form
    citation_of: dict[int, int] = {}
    for wid in selected_ids:
        w = words[wid]
        if w.is_lexical_form and w.lexeme_id is not None:
            citation_of.setdefault(w.lexeme_id, wid)

    entries: list[dict] = []
    stats = {"entries": 0, "with_gloss_ml": 0, "with_example": 0,
             "translit_gaps": 0, "lexical_forms": 0, **la_stats}

    for wid, freq in selected:
        w = words[wid]
        lx = lexemes.get(w.lexeme_id) if w.lexeme_id is not None else None
        rt = roots.get(lx.root_id) if lx and lx.root_id is not None else None
        meanings = [m.text for m in english.get(w.lexeme_id, [])]

        lat = transliterate_latin(w.ascii_voc, lat_table)
        ml = transliterate_malayalam(w.ascii_voc, ml_table)
        # An unmapped token means the draft table has a hole: store None and
        # say so, never a partial string that looks complete (project rule:
        # gaps are marked, not papered over).
        translit_lat = lat.text if lat.ok else None
        translit_ml = ml.text if ml.ok else None
        if not (lat.ok and ml.ok):
            stats["translit_gaps"] += 1

        gloss_ml = pivot(meanings, olam) if meanings else []
        example = matthew.example_for(wid, words)

        prov = dict(_PROVENANCE)
        conf = dict(_CONFIDENCE)
        if not lat.ok:
            prov["translit_lat"] = f"GAP — unmapped tokens {lat.unknown} in {w.ascii_voc!r}"
        if not ml.ok:
            prov["translit_ml"] = f"GAP — unmapped tokens {ml.unknown} in {w.ascii_voc!r}"
        la_entry = added_via_lexical_aids.get(wid)
        if la_entry is not None:
            # This entry wouldn't have made Matthew's own top_n cutoff; it's
            # here because Lexical Aids to the Syriac NT (Kiraz & Lee,
            # Gorgias Press 2024 — data/lexical_aids/PROVENANCE.md) ranks it
            # common across the whole NT. The book's own text is never
            # stored — only this citation and its NT-wide frequency count.
            prov["_selection"] = (
                "Lexical Aids to the Syriac New Testament (Kiraz & Lee, 3rd "
                f"ed., Gorgias Press 2024), ref #{la_entry.ref_no}, "
                f"{la_entry.freq_nt}x across the whole NT — used under IIT "
                "Goa partnership, attested by Ameen 2026-07-05 (written "
                "agreement pending, flagged for Dr. Amaldev)")
            conf["_selection"] = "n/a"

        entries.append({
            "word_id": wid,
            "headword_eastern": None,
            "headword_western": None,
            "headword_bare": w.syriac_cons,
            "sedra3_vocalised": w.ascii_voc,
            "lemma": lx.syriac if lx else None,
            "lexeme_id": w.lexeme_id,
            "root": rt.syriac if rt else None,
            "root_id": lx.root_id if lx else None,
            "pos": lx.category if lx else None,
            "morphology": json.dumps(sedra3.decode_word_features(w.features)),
            "morph_summary": sedra3.morphology_summary(w.features),
            "is_lexical_form": int(w.is_lexical_form),
            "has_seyame": int(w.has_seyame),
            "is_enclitic": int(w.is_enclitic),
            "translit_lat": translit_lat,
            "translit_ml": translit_ml,
            "translit_flags": json.dumps(sorted(lat.flags | ml.flags)),
            "gloss_en": "; ".join(meanings) if meanings else None,
            "gloss_ml": json.dumps(gloss_ml, ensure_ascii=False),
            "freq": freq,
            "example_ref": example["ref"] if example else None,
            "example_text": example["text"] if example else None,
            "example_hl": json.dumps(example["highlight"]) if example else None,
            "lemma_link_word_id":
                citation_of.get(w.lexeme_id) if (w.lexeme_id is not None
                and not w.is_lexical_form) else None,
            "provenance": json.dumps(prov),
            "confidence": json.dumps(conf),
        })
        stats["entries"] += 1
        stats["with_gloss_ml"] += bool(gloss_ml)
        stats["with_example"] += bool(example)
        stats["lexical_forms"] += int(w.is_lexical_form)

    return entries, stats
