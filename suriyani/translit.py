"""Deterministic transliteration driven by human-editable rule tables.

Blueprint anchor: §6.4 fields translit_ml / translit_lat. Design rule
(project-wide): transliteration is a *convention*, and conventions belong
to the experts — here, to the practice fixed in Joju Jacob's slides. So
this module is pure machinery: it tokenises SEDRA III vocalised ASCII
(sedra3.tokenize_vocalised) and applies whatever the TSV tables in
tables/ say. Both shipped tables are DRAFT v0 and say so in their headers;
the engine invents nothing and reports every token it cannot map instead
of guessing.

Latin is a plain token→string concatenation. Malayalam needs a little
state per token because the script is an abugida: a consonant with no
vowel takes the virama (്), the inherent vowel 'a' takes nothing, other
vowels take their matra, and carrier consonants (alaph, and per the draft
table ayin) surface their vowel as an independent letter instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .sedra3 import tokenize_vocalised

VIRAMA = "\u0d4d"          # MALAYALAM SIGN VIRAMA (chandrakkala)
CARRIER = "@carrier"       # table directive, see tables/translit_syr_ml.tsv

# core = consonant symbol + optional qushaya/rukkakha/linea marks,
# then an optional single vowel — and, in one real WORDS.TXT record
# ("B'Ra_T,;"), a mark written AFTER the vowel; group 3 catches those.
# Bare vowels / '*' / '-' handled separately.
_TOKEN_RE = re.compile(r"^([A-Z;/][',_]*)([aoeiu]?)([',_]*)$")


class RuleTable:
    """token → (output, notes), loaded from a TSV with '#' comments.

    An empty output cell is a real mapping (the Malayalam inherent vowel),
    not a missing one — hence the explicit dict membership tests below.
    """

    def __init__(self, path: Path):
        self.path = path
        self.rules: dict[str, str] = {}
        self.notes: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cols = line.split("\t")
            token = cols[0]
            self.rules[token] = cols[1] if len(cols) > 1 else ""
            if len(cols) > 2 and cols[2].strip():
                self.notes[token] = cols[2].strip()

    def lookup_consonant(self, core: str) -> str | None:
        """Resolve a consonant core like "T,", "C'", "A_".

        Qushaya (') means the hard/plain value, and linea (_) is present in
        the data but unapplied in v0 (flagged in the table headers), so both
        are stripped before lookup. Rukkakha (,) selects the soft row when
        the table has one and falls back to the plain letter when it does
        not — the fallback keeps the engine total without inventing rows.
        """
        stripped = core.replace("'", "").replace("_", "")
        if stripped in self.rules:
            return self.rules[stripped]
        base = stripped.replace(",", "")
        if base in self.rules:
            return self.rules[base]
        return None


@dataclass
class TranslitResult:
    text: str
    unknown: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.unknown


def _split(token: str) -> tuple[str, str] | None:
    m = _TOKEN_RE.match(token)
    if m is None:
        return None
    # Marks written after the vowel join the consonant core, so linea
    # still raises its flag and the rule lookup still strips them.
    return (m.group(1) + m.group(3), m.group(2))


def transliterate_latin(vocalised: str, table: RuleTable) -> TranslitResult:
    res = TranslitResult(text="")
    out: list[str] = []
    for tok in tokenize_vocalised(vocalised):
        if tok == "*":
            res.flags.add("seyame-dropped")
            continue
        if tok == "-":
            out.append("-")
            continue
        if tok in "aoeiu":                       # word-initial bare vowel
            out.append(table.rules.get(tok, ""))
            continue
        parts = _split(tok)
        if parts is None:
            res.unknown.append(tok)
            continue
        core, vowel = parts
        if "_" in core:
            res.flags.add("linea-unapplied")
        cons = table.lookup_consonant(core)
        if cons is None:
            res.unknown.append(tok)
            continue
        out.append(cons)
        if vowel:
            out.append(table.rules.get(vowel, ""))
    res.text = "".join(out)
    return res


def transliterate_malayalam(vocalised: str, table: RuleTable) -> TranslitResult:
    res = TranslitResult(text="")
    out: list[str] = []
    for tok in tokenize_vocalised(vocalised):
        if tok == "*":
            res.flags.add("seyame-dropped")
            continue
        if tok == "-":
            out.append("-")
            continue
        if tok in "aoeiu":                       # word-initial bare vowel
            out.append(table.rules.get("^" + tok, ""))
            continue
        parts = _split(tok)
        if parts is None:
            res.unknown.append(tok)
            continue
        core, vowel = parts
        if "_" in core:
            res.flags.add("linea-unapplied")
        cons = table.lookup_consonant(core)
        if cons is None:
            res.unknown.append(tok)
            continue
        if cons == CARRIER:
            if vowel:
                out.append(table.rules.get("^" + vowel, ""))
            continue
        out.append(cons)
        if not vowel:
            out.append(VIRAMA)                   # bare consonant: ക + ് = ക്
        elif vowel != "a":                       # 'a' is the inherent vowel
            out.append(table.rules.get(vowel, ""))
    res.text = "".join(out)
    return res
