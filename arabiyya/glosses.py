"""English glosses for Qur'anic lemmas, matched from Camel Morph MSA.

The Syriac backbone got its English glosses from inside its own resource
(SEDRA's Payne Smith-derived ENGLISH.TXT). QAC 0.4 ships no gloss layer,
so the Arabic side crosses resources: the lemma from QAC is looked up in
the camel_morph MSA lexicon (data/camel/camel-msa-glosses.tsv, MIT — see
its PROVENANCE.md). That is a weaker chain than the Syriac one — an MSA
lexicon glossing Classical/Qur'anic lemmas — so matches carry confidence
"cross_matched", never "source", and every match records which camel lex
it hit and at which tier, for one-glance audit.

Two tiers, both mechanical:

  exact   the vocalised lemma strings are identical (NFC)
  folded  both sides reduced by a documented orthographic fold:
          dagger alef -> plain alef, then all combining marks dropped,
          hamza-seat letters folded to their base (أإٱ→ا, ؤ→و, ئ→ي),
          tatweel dropped. This absorbs convention differences like
          QAC رَحْمٰن vs MSA رَحْمَان without touching display forms.

A lemma with no match keeps gloss_en = None — an honest gap, exactly as
Olam misses did on the Syriac side. The upgrade path (QAC's own GPL
word-by-word glosses, fetched by the project later) is logged in
DECISIONS.md.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

#: camel_morph verb lemmas carry a vocalism suffix ("قَال-ُ" = qāla with
#: imperfect-stem damma). It is class metadata, not orthography: strip it
#: for matching and display.
_VOCALISM_RE = re.compile(r"-[\u064B-\u0652]{0,2}$")

#: The folded tier is only safe for content words. Short function words
#: (particles, pronouns …) collide catastrophically once diacritics are
#: dropped — ثُمَّ "then" would match ثَمّ "there" — so they get the exact
#: tier or nothing.
_CONTENT_TAGS = {"N", "PN", "ADJ", "V"}

_HAMZA_FOLD = str.maketrans({"\u0623": "\u0627",   # أ -> ا
                             "\u0625": "\u0627",   # إ -> ا
                             "\u0671": "\u0627",   # ٱ -> ا
                             "\u0624": "\u0648",   # ؤ -> و
                             "\u0626": "\u064A"})  # ئ -> ي


def fold(arabic: str) -> str:
    """The matching key described in the module docstring. Match-time only;
    never applied to anything a user sees."""
    s = unicodedata.normalize("NFC", arabic).replace("\u0670", "\u0627")
    s = s.replace("\u0622", "\u0627")            # آ -> ا  (madda)
    s = "".join(ch for ch in s if not unicodedata.combining(ch) and ch != "\u0640")
    s = s.translate(_HAMZA_FOLD)
    # hamza written on the line before alef is the other spelling of madda
    # (QAC ءَامَنَ vs MSA آمَن): merge for matching.
    return s.replace("\u0621\u0627", "\u0627")


def _pos_compatible(qac_tag: str, camel_pos: str) -> bool:
    """Coarse cross-tagset compatibility, used to PREFER matches, not to
    exclude them (a pos-mismatched gloss is still shown if it is all we
    have, flagged by its own recorded pos)."""
    if qac_tag == "V":
        return camel_pos.startswith("verb")
    if qac_tag in ("N", "PN"):
        return camel_pos.startswith(("noun", "abbrev"))
    if qac_tag == "ADJ":
        return camel_pos.startswith("adj")
    return True


class CamelGlossIndex:
    def __init__(self, tsv_path: Path):
        self.exact: dict[str, list[tuple[str, str, str]]] = {}
        self.folded: dict[str, list[tuple[str, str, str]]] = {}
        with open(tsv_path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 4:
                    continue
                lex, pos, root, glosses = parts
                lex = _VOCALISM_RE.sub("", lex)
                rec = (lex, pos, glosses)
                self.exact.setdefault(unicodedata.normalize("NFC", lex), []).append(rec)
                self.folded.setdefault(fold(lex), []).append(rec)
                if "\u0670" in lex:
                    # A dagger alef inside an MSA lemma can correspond to
                    # either an explicit alef (رَحْمٰن ~ رَحْمَان) or to
                    # nothing at all in the Qur'anic spelling
                    # (اللَّٰه ~ ٱللَّه) — index both treatments.
                    alt = fold(lex.replace("\u0670", ""))
                    if alt != fold(lex):
                        self.folded.setdefault(alt, []).append(rec)

    def lookup(self, lemma_ar: str, qac_tag: str,
               max_senses: int = 4) -> tuple[str | None, list[dict]]:
        """-> (gloss_en or None, per-match provenance records)."""
        key = unicodedata.normalize("NFC", lemma_ar)
        tiers = [("exact", self.exact, key)]
        if qac_tag in _CONTENT_TAGS:
            tiers.append(("folded", self.folded, fold(lemma_ar)))
        for tier, table, k in tiers:
            recs = table.get(k)
            if not recs:
                continue
            # Proper-noun rows gloss with transliterations ("Min", "Ans");
            # they are only evidence when QAC itself says proper noun.
            if qac_tag != "PN":
                recs = [r for r in recs if r[1] not in ("noun_prop", "abbrev")]
                if not recs:
                    continue
            preferred = [r for r in recs if _pos_compatible(qac_tag, r[1])]
            chosen = preferred or recs
            senses: list[str] = []
            prov: list[dict] = []
            for lex, pos, glosses in chosen[:3]:
                prov.append({"lex": lex, "pos": pos, "tier": tier,
                             "pos_compatible": _pos_compatible(qac_tag, pos)})
                for sense in glosses.split(";"):
                    sense = sense.replace("_", " ").strip()
                    if sense and sense not in senses:
                        senses.append(sense)
            return "; ".join(senses[:max_senses]), prov
        return None, []
