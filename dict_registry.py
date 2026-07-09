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
VERSION = "1.7"


def build_syriac_keyboard() -> dict:
    letters = [{"c": chr(cp), "n": name.replace("SYRIAC LETTER ", "")}
               for cp, name in sedra3._UNICODE_CONSONANTS]
    # EAST Syriac (Madnhāyā) marks only — this dictionary's declared
    # script. Unicode's own names carry the taxonomy: the dot-based vowel
    # signs (… DOTTED, DOTTED ZLAMA …, RWAHA) are the Eastern system; the
    # PTHAHA/ZQAPHA/RBASA/HBASA/ESASA ABOVE/BELOW pairs are the Western
    # (Serṭā-era) signs a Madnhāyā keyboard shouldn't offer — the same
    # script-vetting rule that removed the Khowar letters from the Arabic
    # keyboard. Qushshaya/rukkakha/feminine dot/seyame are common East
    # Syriac orthography. VERIFY with Joju Jacob's slides before treating
    # this set as final (audit 2026-07-09; typed points are stripped for
    # consonantal matching either way, so search never depends on them).
    east_points = [
        0x0732,  # PTHAHA DOTTED
        0x0735,  # ZQAPHA DOTTED
        0x0738,  # DOTTED ZLAMA HORIZONTAL
        0x0739,  # DOTTED ZLAMA ANGULAR
        0x073C,  # HBASA-ESASA DOTTED
        0x073F,  # RWAHA
        0x0740,  # FEMININE DOT
        0x0741,  # QUSHSHAYA
        0x0742,  # RUKKAKHA
        0x0308,  # seyame (COMBINING DIAERESIS)
    ]
    points = []
    for cp in east_points:
        ch = chr(cp)
        name = unicodedata.name(ch)   # raises on a bad codepoint: verifiable
        points.append({"c": ch,
                       "n": name.replace("SYRIAC ", "").replace("COMBINING ", "")})
    return {"letters": letters, "points": points}


def build_arabic_keyboard() -> dict:
    # Two vetted ranges, NOT one: U+063B–U+063F are Keheh/Farsi-Yeh
    # variants for other languages' orthographies (Khowar, Persian-adjacent)
    # that a naive 0621–064A sweep would include — none of them occurs in
    # the Qur'anic text, and a key that can never match anything is a trap
    # (verified against the compiled store's surface index, 2026-07-09;
    # tests/test_app.py pins every key to an attested character).
    letters = []
    for cp in (list(range(0x0621, 0x063B))        # ء hamza … غ ghain
               + list(range(0x0641, 0x064B))      # ف feh … ي yeh
               + [0x0671]):                       # ٱ alef wasla (Uthmani)
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
    wiktionary_related_pattern: str        # regex over L2 headings for related languages
    wikidata_lang_labels: tuple[str, ...]  # Wikidata lexeme language names to keep
    translation_codes: tuple[str, ...]     # Wiktionary {{t|CODE|…}} codes for
                                           # English→target translation lookups
    wikipedia_host: str                    # the language's own Wikipedia
    wikipedia_label: str                   # panel label for that source

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
    # No Wikidata: Classical Syriac lexemes are still too sparse there to
    # be worth a query (verified empty, 2026-07-07). Wiktionary's exact
    # entry + related-page search cover the Syriac side.
    online_sources=("wiktionary", "wiktionary_search", "wikipedia"),
    wiktionary_lang_candidates=("Classical Syriac", "Syriac"),
    # Related Aramaic varieties whose sections share the page (verified on
    # the fixture page for ܫܠܡܐ: Assyrian Neo-Aramaic, Turoyo, Western
    # Neo-Aramaic) — shown labelled, never merged with Classical Syriac.
    wiktionary_related_pattern=r"Aramaic$|^Turoyo$",
    wikidata_lang_labels=("Classical Syriac", "Syriac"),
    # syc translations are near-absent on en.wiktionary (verified
    # 2026-07-09); Assyrian Neo-Aramaic and Turoyo do appear and share the
    # script — each result is labelled with its own language name.
    translation_codes=("syc", "aii", "tru"),
    # Aramaic Wikipedia (arc) is written in Syriac script and has real
    # articles for common words (verified live 2026-07-09: ܡܠܟܐ, ܫܠܡܐ).
    wikipedia_host="arc.wikipedia.org",
    wikipedia_label="Wikipedia (Aramaic) — encyclopedia",
)

ARABIC = DictConfig(
    slug="arabic",
    db_filename="dictionary_ar.db",
    script="arabic",
    font_class="ar",
    keyboard_builder=build_arabic_keyboard,
    other_slug="syriac",
    other_label="East Syriac → Malayalam",
    online_sources=("wiktionary", "wiktionary_search", "wikipedia", "wikidata"),
    wiktionary_lang_candidates=("Arabic",),
    # Dialect sections ("Egyptian Arabic", "South Levantine Arabic", …)
    # share the page; keep them, labelled. Persian/Urdu/Ottoman Turkish
    # sections of the same spelling stay excluded.
    wiktionary_related_pattern=r"Arabic$",
    wikidata_lang_labels=("Arabic",),
    translation_codes=("ar",),
    wikipedia_host="ar.wikipedia.org",
    wikipedia_label="Wikipedia (Arabic) — encyclopedia",
)

DICTS = {SYRIAC.slug: SYRIAC, ARABIC.slug: ARABIC}
