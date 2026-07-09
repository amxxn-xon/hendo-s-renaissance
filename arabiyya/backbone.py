"""The Arabic backbone adapter: QAC 0.4 → §6.4 entry records.

This module is the proof of the contract written in suriyani/backbone.py:
`assemble_entries(repo_root, top_n)` returns dicts with *exactly* the same
ENTRY_FIELDS keys (imported from there and asserted), so compile, store
schema, lookup, app and exporter carry over without modification. Where a
field name is Syriac-flavoured, the Arabic value occupies the same
semantic slot:

    headword_eastern   the vocalised display headword. For Syriac this
                       waits on a SEDRA IV fetch; here it is present at
                       build time, because QAC's forms ARE the vocalised
                       Uthmani orthography — nothing to fetch, nothing
                       to synthesize.
    sedra3_vocalised   "the source's own encoding of the vocalised form":
                       the extended-Buckwalter string, verbatim.
    headword_bare      the consonantal search skeleton.
    lexeme_id/root_id  SEDRA record numbers on the Syriac side; here QAC
                       carries no ids, so distinct lemmas/roots are
                       enumerated deterministically at build time.
    has_seyame, is_enclitic   Syriac-only distinctions: constant 0.

Gloss chain difference, carried in the labels: gloss_en is cross-matched
from the camel_morph MSA lexicon (confidence "cross_matched", never
"source"), and gloss_ml is the same Olam machine-draft pivot the Syriac
side uses — the shared tail staying shared.
"""

from __future__ import annotations

import json
from pathlib import Path

from suriyani import ipa
from suriyani.backbone import ENTRY_FIELDS
from suriyani.olam import OlamIndex, pivot
from suriyani.translit import RuleTable

from .buckwalter import skeleton, strip_lemma_index, to_arabic

#: shared symbol→IPA table (the romanization symbol inventory is common to
#: both dictionaries; see tables/translit_ipa.tsv — DRAFT v0, UNVETTED)
_IPA_TABLE_PATH = Path(__file__).resolve().parent.parent / "tables" / "translit_ipa.tsv"
from .glosses import CamelGlossIndex
from .qac import POS_NAMES, QuranCorpus, WordToken
from .translit_ar import transliterate_latin_ar, transliterate_malayalam_ar

_PROVENANCE = {
    "headword_eastern": "QAC 0.4 word form (vocalised Uthmani orthography), "
                        "Buckwalter→Unicode per verified table",
    "headword_bare": "consonantal skeleton of the QAC form (marks and "
                     "Qur'anic annotation dropped; wasla folded)",
    "sedra3_vocalised": "QAC 0.4 word form, extended Buckwalter, verbatim",
    "headword_western": "not applicable to the Arabic backbone",
    "lemma": "QAC 0.4 LEM (stem segment), Buckwalter→Unicode",
    "root": "QAC 0.4 ROOT (stem segment), Buckwalter→Unicode",
    "pos": "QAC 0.4 stem tag (readable label per QAC tag set; raw tag kept "
           "in morphology)",
    "morphology": "QAC 0.4 feature codes, decoded per documented tag set; "
                  "unrecognised codes kept verbatim",
    "gloss_en": "camel_morph MSA v1.0 lexicon (MIT), matched on lemma — "
                "cross-resource match, see per-match records",
    "gloss_ml": "Olam English→Malayalam pivot (ODbL); machine draft, unvalidated",
    "translit_lat": "rule table tables/translit_ara_lat.tsv — DRAFT v0, UNVETTED",
    "translit_ml": "rule table tables/translit_ara_ml.tsv — DRAFT v0, UNVETTED",
    "translit_ipa": "rule table tables/translit_ipa.tsv over translit_lat — DRAFT v0, UNVETTED",
    "example": "Qur'an, first attestation; verse rendered from QAC forms "
               "(vocalised), cited sura:aya",
}

_CONFIDENCE = {
    "headword_eastern": "source",
    "headword_bare": "source",
    "sedra3_vocalised": "source",
    "headword_western": "n/a",
    "lemma": "source",
    "root": "source",
    "pos": "source",
    "morphology": "decoded",
    "gloss_en": "cross_matched",
    "gloss_ml": "machine_draft",
    "translit_lat": "draft_unvetted",
    "translit_ml": "draft_unvetted",
    "translit_ipa": "draft_unvetted",
    "example": "source",
}

#: Written once into store meta by compile_arabic.py; rows carry overrides.
PROVENANCE_BASE = _PROVENANCE
CONFIDENCE_BASE = _CONFIDENCE


def _morphology(t: WordToken) -> tuple[dict, str]:
    """Word token → (morphology dict, one-line summary)."""
    st = t.stem
    m: dict[str, object] = {"stem_tag": st.tag, **st.flags}
    prefixes = [{"form": s.form_ar, "tag": s.tag,
                 "labels": s.flags.get("labels", [])}
                for s in t.segments if s.disc == "PREFIX"]
    suffixes = [{"form": s.form_ar, "tag": s.tag,
                 "labels": s.flags.get("labels", [])}
                for s in t.segments if s.disc == "SUFFIX"]
    if prefixes:
        m["prefixes"] = prefixes
    if suffixes:
        m["suffixes"] = suffixes
    if t.n_stems > 1:
        m["compound_stems"] = t.n_stems

    parts: list[str] = []
    f = st.flags
    if "verb_form" in f:
        parts.append(f"form {f['verb_form']}")
    for key in ("aspect", "voice", "mood"):
        if key in f:
            parts.append(str(f[key]))
    if f.get("participle"):
        parts.append("participle")
    if f.get("verbal_noun"):
        parts.append("verbal noun")
    for key in ("person", "gender", "number", "case"):
        if key in f:
            parts.append(str(f[key]))
    if f.get("definiteness"):
        parts.append(str(f["definiteness"]))
    for p in prefixes:
        parts.append(f"+ prefix {p['form']}")
    for s in suffixes:
        labels = ",".join(s["labels"]) if s["labels"] else s["tag"]
        parts.append(f"+ suffix {s['form']} ({labels})")
    if t.n_stems > 1:
        parts.append("compound (two stems)")
    return m, ", ".join(parts)


def assemble_entries(repo_root: Path, top_n: int) -> tuple[list[dict], dict]:
    """Top-n most frequent Qur'an word analyses → entry dicts.

    Deterministic: frequency descending, first-attestation order breaking
    ties, ids enumerated over that order — two builds from the same data
    are identical, same as the Syriac compile.
    """
    corpus = QuranCorpus.load(repo_root / "data" / "qac" /
                              "quranic-corpus-morphology-0.4.txt")
    glosses = CamelGlossIndex(repo_root / "data" / "camel" /
                              "camel-msa-glosses.tsv")
    olam = OlamIndex(repo_root / "data" / "olam" / "olam-enml.tsv")
    lat_table = RuleTable(repo_root / "tables" / "translit_ara_lat.tsv")
    ml_table = RuleTable(repo_root / "tables" / "translit_ara_ml.tsv")

    ranked = sorted(
        corpus.top(top_n),
        key=lambda sn: (-sn[1],
                        (corpus.first_seen[sn[0]].chapter,
                         corpus.first_seen[sn[0]].verse,
                         corpus.first_seen[sn[0]].word_pos)))

    # deterministic id spaces for lemmas and roots over the selected slice
    lemma_ids: dict[str, int] = {}
    root_ids: dict[str, int] = {}
    reps: list[tuple[tuple, int, WordToken]] = []
    for sig, freq in ranked:
        t = corpus.first_seen[sig]
        reps.append((sig, freq, t))
        st = t.stem
        if st.lem_bw:
            lem = to_arabic(strip_lemma_index(st.lem_bw))
            lemma_ids.setdefault(lem, len(lemma_ids) + 1)
        if st.root_bw:
            root_ids.setdefault(to_arabic(st.root_bw), len(root_ids) + 1)

    # citation-form links: first compiled entry per lemma whose form IS the
    # bare lemma (single segment, matching skeletons)
    def is_citation(t: WordToken, lem: str | None) -> bool:
        return (lem is not None and len(t.segments) == 1
                and skeleton(t.form_ar) == skeleton(lem))

    citation_of: dict[int, int] = {}
    for word_id, (sig, freq, t) in enumerate(reps, start=1):
        st = t.stem
        lem = to_arabic(strip_lemma_index(st.lem_bw)) if st.lem_bw else None
        if lem and is_citation(t, lem):
            citation_of.setdefault(lemma_ids[lem], word_id)

    entries: list[dict] = []
    stats = {"entries": 0, "with_gloss_en": 0, "with_gloss_ml": 0,
             "with_example": 0, "translit_gaps": 0, "lexical_forms": 0}

    for word_id, (sig, freq, t) in enumerate(reps, start=1):
        st = t.stem
        form_ar = t.form_ar
        lem = to_arabic(strip_lemma_index(st.lem_bw)) if st.lem_bw else None
        root = to_arabic(st.root_bw) if st.root_bw else None
        morph, summary = _morphology(t)

        gloss_en, gloss_prov = (glosses.lookup(lem, st.tag)
                                if lem else (None, []))
        gloss_ml = (pivot([s.strip() for s in gloss_en.split(";")], olam)
                    if gloss_en else [])

        lat = transliterate_latin_ar(form_ar, lat_table)
        ml = transliterate_malayalam_ar(form_ar, ml_table)
        translit_lat = lat.text if lat.ok else None
        translit_ml = ml.text if ml.ok else None
        if not (lat.ok and ml.ok):
            stats["translit_gaps"] += 1

        example = corpus.example_for(sig)
        attestations = corpus.attestations_for(sig, limit=8)  # size: see suriyani/backbone.py
        if attestations["total"] <= 1:
            attestations = {"total": attestations["total"], "shown": []}
        lexical = is_citation(t, lem)

        # Overrides only — the constant baseline lives once in meta
        # (provenance_base / confidence_base; see suriyani/backbone.py).
        prov: dict = {}
        if gloss_prov:
            prov["gloss_en"] = {"source": _PROVENANCE["gloss_en"],
                                "matches": gloss_prov}
        if not lat.ok:
            prov["translit_lat"] = f"GAP — unmapped {lat.unknown} in {form_ar!r}"
        if not ml.ok:
            prov["translit_ml"] = f"GAP — unmapped {ml.unknown} in {form_ar!r}"

        entries.append({
            "word_id": word_id,
            "headword_eastern": form_ar,
            "headword_western": None,
            "headword_bare": skeleton(form_ar),
            "sedra3_vocalised": t.form_bw,
            "lemma": lem,
            "lexeme_id": lemma_ids.get(lem) if lem else None,
            "root": root,
            "root_id": root_ids.get(root) if root else None,
            "pos": POS_NAMES.get(st.tag, st.tag),
            "morphology": json.dumps(morph, ensure_ascii=False),
            "morph_summary": summary,
            "is_lexical_form": int(lexical),
            "has_seyame": 0,
            "is_enclitic": 0,
            "translit_lat": translit_lat,
            "translit_ml": translit_ml,
            "translit_ipa": ipa.render(translit_lat, _IPA_TABLE_PATH),
            "translit_flags": json.dumps(sorted(lat.flags | ml.flags)),
            "gloss_en": gloss_en,
            "gloss_ml": json.dumps(gloss_ml, ensure_ascii=False),
            "freq": freq,
            "example_ref": example["ref"] if example else None,
            "example_text": example["text"] if example else None,
            "example_hl": json.dumps(example["highlight"]) if example else None,
            "attestations": json.dumps(attestations, ensure_ascii=False),
            "lemma_link_word_id":
                citation_of.get(lemma_ids[lem]) if (lem and not lexical) else None,
            "provenance": json.dumps(prov, ensure_ascii=False),
            "confidence": "{}",   # no per-entry overrides; base lives in meta
        })
        stats["entries"] += 1
        stats["with_gloss_en"] += bool(gloss_en)
        stats["with_gloss_ml"] += bool(gloss_ml)
        stats["with_example"] += bool(example)
        stats["lexical_forms"] += int(lexical)

    # the contract, enforced
    for e in entries[:1]:
        assert list(e.keys()) == ENTRY_FIELDS, "entry keys drifted from the contract"
    return entries, stats
