"""IPA rendering of the stored Latin transliterations — engine only.

Engines vs tables (DECISIONS №21): every sound value lives in the
human-editable tables/translit_ipa.tsv (DRAFT v0, UNVETTED — flagged for a
convention owner); this module only applies it, longest source sequence
first, and adds no mappings of its own. If a transliteration contains any
symbol the table doesn't list, the whole word gets NO IPA rather than a
partial or guessed one — no gloss beats a wrong gloss (№20).

Runs at compile time (both backbones call render()); the lookup app only
ever SELECTs the stored result.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path


def load_table(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        src, out = parts[0], parts[1]
        if src == "" or out == "":
            continue
        assert src not in table, f"duplicate IPA rule for {src!r}"
        table[src] = out
    assert table, f"empty IPA table at {path}"
    return table


@lru_cache(maxsize=4)
def _cached_table(path_str: str) -> tuple[dict[str, str], int]:
    table = load_table(Path(path_str))
    return table, max(len(k) for k in table)


def render(translit_lat: str | None, table_path: Path) -> str | None:
    """translit_lat -> IPA string, or None (honest gap) on any symbol the
    table doesn't cover. NFC first so decomposed vowel+macron sequences
    match the composed table keys."""
    if not translit_lat:
        return None
    table, max_len = _cached_table(str(table_path))
    s = unicodedata.normalize("NFC", translit_lat)
    out: list[str] = []
    i = 0
    while i < len(s):
        for width in range(min(max_len, len(s) - i), 0, -1):
            piece = s[i:i + width]
            if piece in table:
                out.append(table[piece])
                i += width
                break
        else:
            return None          # unmapped symbol: no IPA at all
    return "".join(out)
