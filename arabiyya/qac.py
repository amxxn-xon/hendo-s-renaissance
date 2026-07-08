"""The Qur'an as a corpus, read faithfully from QAC morphology 0.4.

The Arabic twin of suriyani/corpus.py + the record-parsing half of
sedra3.py, playing the role BFBS.TXT played for Syriac: every running
word of the text is already segmented and analysed by the corpus editors,
so frequency counting, examples, and lemma links all inherit expert
judgement instead of ours.

One structural difference from the Syriac side is worth understanding.
SEDRA gives each analysed word a database id, and the NT text points at
those ids; QAC instead repeats the full analysis inline at every
occurrence. So the notion of "one dictionary entry" has to be
reconstructed: two occurrences belong to the same entry when they have
the same *analysis signature* — the same written form AND the same
segment-by-segment analysis (discriminator, tag, lemma). Same spelling
with a different reading stays distinct, which is exactly what feeds the
ranked-candidates view, just as SEDRA's separate word records did.

Everything here is conversion and bookkeeping; nothing is interpretation.
The morphology decoder maps QAC's documented flag codes to readable
words and keeps any code it does not recognise verbatim, so no
information is invented and none is lost.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .buckwalter import strip_lemma_index, to_arabic

# --- feature decoding -------------------------------------------------------
# Flag inventory verified empirically over the whole file (see tests).
# QAC marks verb form I and active voice by absence; we surface only what
# the data says.

_CASE = {"NOM": "nominative", "GEN": "genitive", "ACC": "accusative"}
_ASPECT = {"PERF": "perfect", "IMPF": "imperfect", "IMPV": "imperative"}
_VOICE = {"ACT": "active", "PASS": "passive"}
_MOOD = {"IND": "indicative", "SUBJ": "subjunctive", "JUS": "jussive"}
_GENDER = {"M": "masculine", "F": "feminine"}
_NUMBER = {"S": "singular", "D": "dual", "P": "plural"}
_PERSON = {"1": "first", "2": "second", "3": "third"}

# Part-of-speech tags, transcribed from the QAC documentation tag set
# (corpus.quran.com/documentation/tagset.jsp). The raw tag is always kept
# alongside, so a mistranscribed label here is cosmetic, not lossy.
POS_NAMES = {
    "N": "noun", "PN": "proper noun", "ADJ": "adjective", "V": "verb",
    "PRON": "pronoun", "DEM": "demonstrative pronoun",
    "REL": "relative pronoun", "P": "preposition", "CONJ": "conjunction",
    "DET": "determiner", "T": "time adverb", "LOC": "location adverb",
    "NEG": "negative particle", "EMPH": "emphatic particle",
    "INTG": "interrogative particle", "COND": "conditional particle",
    "SUB": "subordinating conjunction", "ACC": "accusative particle",
    "VOC": "vocative particle", "CERT": "particle of certainty",
    "FUT": "future particle", "REM": "resumption particle",
    "RES": "restriction particle", "RSLT": "result particle",
    "CAUS": "particle of cause", "CIRC": "circumstantial particle",
    "PRP": "purpose particle", "PRO": "prohibition particle",
    "EXP": "exceptive particle", "AMD": "amendment particle",
    "ANS": "answer particle", "AVR": "aversion particle",
    "COM": "comitative particle", "EQ": "equalization particle",
    "EXH": "exhortation particle", "EXL": "explanation particle",
    "IMPV": "imperative particle", "IMPN": "imperative verbal noun",
    "INC": "inceptive particle", "INT": "particle of interpretation",
    "INL": "Quranic initials", "PREV": "preventive particle",
    "RET": "retraction particle", "SUP": "supplemental particle",
    "SUR": "surprise particle",
}


def _decode_flags(flags: list[str]) -> dict[str, object]:
    """Bare feature codes -> readable dict; unrecognised codes kept verbatim."""
    out: dict[str, object] = {}
    other: list[str] = []
    for f in flags:
        if f in _CASE:
            out["case"] = _CASE[f]
        elif f in _ASPECT:
            out["aspect"] = _ASPECT[f]
        elif f in _VOICE:
            out["voice"] = _VOICE[f]
        elif f == "INDEF":
            out["definiteness"] = "indefinite"
        elif f == "PCPL":
            out["participle"] = True
        elif f == "VN":
            out["verbal_noun"] = True
        elif f.startswith("(") and f.endswith(")"):
            out["verb_form"] = f.strip("()")          # II … XII; I is unmarked
        elif f and f[0] in _PERSON and all(c in "123MFSDP" for c in f):
            # fused person-gender-number codes: 3MS, 1P, 2FD …
            out["person"] = _PERSON[f[0]]
            for c in f[1:]:
                if c in _GENDER:
                    out["gender"] = _GENDER[c]
                elif c in _NUMBER:
                    out["number"] = _NUMBER[c]
        elif f and all(c in "MFSDP" for c in f):
            # gender/number without person: M, MP, FS, MD …
            for c in f:
                if c in _GENDER:
                    out["gender"] = _GENDER[c]
                elif c in _NUMBER:
                    out["number"] = _NUMBER[c]
        else:
            other.append(f)
    if other:
        out["other_flags"] = other
    return out


# --- data model --------------------------------------------------------------

@dataclass
class Segment:
    seg_no: int
    form_bw: str
    tag: str
    disc: str                      # PREFIX | STEM | SUFFIX
    lem_bw: str | None             # with any homograph index still attached
    root_bw: str | None
    flags: dict[str, object]
    raw_features: str

    @property
    def form_ar(self) -> str:
        return to_arabic(self.form_bw)


@dataclass
class WordToken:
    """One running word of the text: location + its ordered segments."""
    chapter: int
    verse: int
    word_pos: int
    segments: list[Segment]

    @property
    def form_bw(self) -> str:
        return "".join(s.form_bw for s in self.segments)

    @property
    def form_ar(self) -> str:
        return to_arabic(self.form_bw)

    @property
    def stem(self) -> Segment:
        """The primary stem. 486 words carry two STEM segments (fused
        compounds like yawma-ʾidhin); we take the first for lemma/root/pos
        and note the compounding in the morphology dict — see DECISIONS."""
        return next(s for s in self.segments if s.disc == "STEM")

    @property
    def n_stems(self) -> int:
        return sum(1 for s in self.segments if s.disc == "STEM")

    @property
    def signature(self) -> tuple:
        """Entry identity: written form + per-segment analysis."""
        return (self.form_bw,
                tuple((s.disc, s.tag, s.lem_bw) for s in self.segments))


def _parse_segment(seg_no: int, form: str, tag: str, feats: str) -> Segment:
    parts = feats.split("|")
    disc = parts[0]
    lem = root = None
    flags: list[str] = []
    for f in parts[1:]:
        if f.startswith("LEM:"):
            lem = f[4:]
        elif f.startswith("ROOT:"):
            root = f[5:]
        elif f.startswith("POS:"):
            pass                                # duplicates the TAG column
        elif ":" in f or f.endswith("+") or f.startswith("+"):
            flags.append(f)                     # prefix/suffix labels, MOOD:, SP:, PRON: — kept raw
        else:
            flags.append(f)
    decoded = _decode_flags([f for f in flags if ":" not in f
                             and not f.endswith("+") and not f.startswith("+")])
    raw_labels = [f for f in flags if ":" in f or f.endswith("+") or f.startswith("+")]
    if raw_labels:
        decoded["labels"] = raw_labels          # e.g. Al+, bi+, PRON:3MS, MOOD:IND
    # MOOD is worth surfacing readably on top of the raw label
    for lab in raw_labels:
        if lab.startswith("MOOD:"):
            decoded["mood"] = _MOOD.get(lab[5:], lab[5:])
    return Segment(seg_no, form, tag, disc, lem, root, decoded, feats)


# --- the corpus ---------------------------------------------------------------

class QuranCorpus:
    """The whole text, indexed for the compiler. Loads in ~2 s."""

    def __init__(self, tokens: list[WordToken]):
        self.tokens = tokens
        self.freq: Counter[tuple] = Counter(t.signature for t in tokens)
        self.first_seen: dict[tuple, WordToken] = {}
        for t in tokens:                        # file order == mushaf order
            self.first_seen.setdefault(t.signature, t)
        self.verses: dict[tuple[int, int], list[WordToken]] = defaultdict(list)
        for t in tokens:
            self.verses[(t.chapter, t.verse)].append(t)
        for vt in self.verses.values():
            vt.sort(key=lambda t: t.word_pos)
        #: signature -> every distinct (chapter, verse) it appears in, mushaf
        #: order — built once so attestations_for() is a lookup, not a rescan.
        self.sig_verses: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        _sv_seen: set[tuple] = set()
        for t in tokens:                        # file order == mushaf order
            key = (t.signature, t.chapter, t.verse)
            if key not in _sv_seen:
                _sv_seen.add(key)
                self.sig_verses[t.signature].append((t.chapter, t.verse))

    @classmethod
    def load(cls, path: Path) -> "QuranCorpus":
        words: dict[tuple[int, int, int], list[Segment]] = defaultdict(list)
        order: list[tuple[int, int, int]] = []
        for line in open(path, encoding="utf-8"):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#") or line.startswith("LOCATION"):
                continue
            loc, form, tag, feats = line.split("\t")
            c, v, w, s = map(int, loc.strip("()").split(":"))
            key = (c, v, w)
            if key not in words:
                order.append(key)
            words[key].append(_parse_segment(s, form, tag, feats))
        tokens = []
        for (c, v, w) in order:
            segs = sorted(words[(c, v, w)], key=lambda s: s.seg_no)
            tokens.append(WordToken(c, v, w, segs))
        return cls(tokens)

    def top(self, n: int) -> list[tuple[tuple, int]]:
        return self.freq.most_common(n)

    def example_for(self, sig: tuple) -> dict | None:
        """First attestation, as a display-ready example.

        Unlike the Syriac side — where SEDRA's abstract vowel scheme forced
        consonantal-only verse display — the QAC forms ARE the fully
        vocalised Uthmani orthography, so the verse renders vocalised,
        faithfully, with zero synthesis.
        """
        t0 = self.first_seen.get(sig)
        if t0 is None:
            return None
        return self._render_verse(t0.chapter, t0.verse, sig)

    def _render_verse(self, chapter: int, verse_no: int, sig: tuple) -> dict:
        verse = self.verses[(chapter, verse_no)]
        return {
            "ref": f"Qur'an {chapter}:{verse_no}",
            "text": " ".join(t.form_ar for t in verse),
            "highlight": [i for i, t in enumerate(verse) if t.signature == sig],
        }

    def attestations_for(self, sig: tuple, limit: int = 20) -> dict:
        """Every verse (up to `limit`) where this word occurs, mushaf order
        — the full concordance within the Qur'an, rendered vocalised like
        example_for(). Returns {"total": N, "shown": [{ref,text,highlight}]}."""
        verses = self.sig_verses.get(sig, [])
        shown = [self._render_verse(c, v, sig) for c, v in verses[:limit]]
        return {"total": len(verses), "shown": shown}
