"""Machine-drafted Malayalam gloss candidates via the Olam pivot.

Blueprint anchor: §6.3 — drafting glosses is the automatable grunt work,
and §6.4's gloss_ml field. The route is: SEDRA III's English meaning
(Payne Smith-derived) → exact lookup in the Olam English→Malayalam
dataset → candidate Malayalam definitions. Every candidate is tagged with
the exact English key that matched, so a reviewer can audit the chain
SEDRA-meaning → key → Olam-row in seconds.

Deliberately dumb: exact matching plus two light normalisations (split a
multi-sense meaning on commas/semicolons; drop a leading "to " from verb
meanings). No stemming, no embeddings, no model. A miss leaves gloss_ml
empty — an honest gap beats a fabricated gloss (project rule).
"""

from __future__ import annotations

import re
from pathlib import Path


class OlamIndex:
    """lower-cased English entry → [(pos, malayalam_definition), ...]"""

    def __init__(self, tsv_path: Path):
        self.by_english: dict[str, list[tuple[str, str]]] = {}
        with open(tsv_path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 3:
                    continue
                en, pos, ml = parts
                if en and ml:
                    self.by_english.setdefault(en.lower(), []).append((pos, ml))

    def __len__(self) -> int:
        return len(self.by_english)


def pivot_keys(meaning: str) -> list[str]:
    """English keys to try for one SEDRA meaning string, most-specific first.

    "to set, put, place" -> ["to set, put, place", "to set", "put", "place",
                             "set"]  (parenthetical comments stripped first)
    """
    m = re.sub(r"\([^)]*\)", " ", meaning).strip().lower()
    m = " ".join(m.split())
    if not m:
        return []
    keys = [m]
    for part in re.split(r"[,;]", m):
        p = part.strip()
        if p and p not in keys:
            keys.append(p)
    for k in list(keys):
        if k.startswith("to ") and k[3:] not in keys:
            keys.append(k[3:])
    return keys


def pivot(meanings: list[str], index: OlamIndex, limit: int = 3) -> list[dict]:
    """Candidate glosses: [{"ml", "pos", "english_key"}, ...], ≤ limit,
    deduplicated on the Malayalam string, in meaning order."""
    out: list[dict] = []
    seen: set[str] = set()
    for meaning in meanings:
        for key in pivot_keys(meaning):
            for pos, ml in index.by_english.get(key, []):
                if ml in seen:
                    continue
                seen.add(ml)
                out.append({"ml": ml, "pos": pos, "english_key": key})
                if len(out) >= limit:
                    return out
    return out
