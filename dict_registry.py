"""The two dictionaries, registered once.

Single source of truth for what used to be split across app.py and
app_arabic.py (which imported app.py and monkey-patched DB_PATH and the
keyboard). Each DictConfig names a store, a script, and how to build its
on-screen reference keyboard — nothing here changes what the keyboards
contain, it only gives app.py one place to construct both.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from suriyani import sedra3

ROOT = Path(__file__).resolve().parent

#: Single source of truth for the app version — rendered in the header
#: badge (base.html via app.py's context processor) and sent as the
#: User-Agent version by online_lookup.py.
VERSION = "1.0"


def build_syriac_keyboard() -> dict:
    letters = [{"c": chr(cp), "n": name.replace("SYRIAC LETTER ", "")}
               for cp, name in sedra3._UNICODE_CONSONANTS]
    points = []
    for cp in list(range(0x0730, 0x074B)) + [0x0308]:
        ch = chr(cp)
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        points.append({"c": ch,
                       "n": name.replace("SYRIAC ", "").replace("COMBINING ", "")})
    return {"letters": letters, "points": points}


def build_arabic_keyboard() -> dict:
    letters = []
    for cp in list(range(0x0621, 0x064B)) + [0x0671]:      # ء … ي, plus ٱ
        ch = chr(cp)
        if unicodedata.category(ch) != "Lo":               # skips tatweel
            continue
        letters.append({"c": ch,
                        "n": unicodedata.name(ch).replace("ARABIC LETTER ", "")})
    points = []
    for cp in list(range(0x064B, 0x0653)) + [0x0670]:      # harakat + dagger
        ch = chr(cp)
        points.append({"c": ch,
                       "n": unicodedata.name(ch).replace("ARABIC ", "")
                                                .replace("LETTER ", "")})
    return {"letters": letters, "points": points}


@dataclass(frozen=True)
class DictConfig:
    slug: str                          # URL prefix segment: /<slug>/...
    db_filename: str                   # under data/
    script: str                        # matches the store's own meta['script']
    font_class: str                    # CSS class for headwords/lemma/root
    keyboard_builder: Callable[[], dict]
    other_slug: str
    other_label: str                   # shown on the toggle link
    online_sources: tuple[str, ...]    # which online_lookup.py sources to query
    wiktionary_lang_candidates: tuple[str, ...]  # Wiktionary L2 headings to look for

    @property
    def db_path(self) -> Path:
        return ROOT / "data" / self.db_filename


SYRIAC = DictConfig(
    slug="syriac",
    db_filename="dictionary.db",
    script="syriac",
    font_class="syr",
    keyboard_builder=build_syriac_keyboard,
    other_slug="arabic",
    other_label="Arabic → Malayalam",
    online_sources=("cal", "wiktionary"),
    wiktionary_lang_candidates=("Classical Syriac", "Syriac"),
)

ARABIC = DictConfig(
    slug="arabic",
    db_filename="dictionary_ar.db",
    script="arabic",
    font_class="ar",
    keyboard_builder=build_arabic_keyboard,
    other_slug="syriac",
    other_label="East Syriac → Malayalam",
    online_sources=("wiktionary",),  # CAL is Aramaic-only, not Arabic
    wiktionary_lang_candidates=("Arabic",),
)

DICTS = {SYRIAC.slug: SYRIAC, ARABIC.slug: ARABIC}
