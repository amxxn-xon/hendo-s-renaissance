"""Live, read-only lookups from CAL and Wiktionary — a deliberate, narrow
exception to compile/lookup separation (CLAUDE.md rule #3), made only
after explicit discussion with Ameen about the tradeoff (DECISIONS.md
№28). This module is NOT part of the compiled dictionary: nothing here
is stored, nothing here feeds a compiled entry's own gloss/confidence,
and the app renders its results in a section labelled, unmissably, as
live and unvetted. If a source here is unreachable or returns nothing,
the compiled dictionary's own behaviour (suriyani.lookup.resolve()/
suggest()) is completely unaffected — the two code paths never touch;
this module never imports sqlite3 and is never given a db connection.

Sources, both verified live this session (see DECISIONS.md №28 for the
exact queries run and what came back):

  CAL — the Comprehensive Aramaic Lexicon (cal.huc.edu). Free, keyless,
        no documented API: this queries its public browse CGI
        (browseSKEYheaders.php) and parses the HTML it returns. Aramaic
        only (Syriac's language family) — never queried for the Arabic
        dictionary; Arabic is a related but distinct language.
  Wiktionary — the public MediaWiki API (en.wiktionary.org), used for
        both dictionaries. Free, keyless, documented
        (https://www.mediawiki.org/wiki/API:Parsing_wikitext).
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import asdict, dataclass

from dict_registry import VERSION
from suriyani import sedra3

_USER_AGENT = f"suriyani-dict/{VERSION} (academic; Hendo Projects; online-lookup)"

# Probe the dependency once at import, so a machine without `requests`
# reports the honest cause ("package not installed") rather than every
# lookup claiming a transient network failure for a site never contacted.
try:
    import requests as _requests
except ImportError:
    _requests = None

_NO_REQUESTS_MSG = ("online lookups need the 'requests' package "
                    "(pip install -r requirements.txt)")

#: Hard ceiling on how much of an external response we buffer + parse. Both
#: sources' real responses are a few KB; anything past this is a maintenance
#: page, an error dump, or a hostile body, and is not worth pinning a worker
#: over. Enforced by streaming and stopping early (see _get_capped).
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _get_capped(url: str, params: dict, timeout: float) -> "tuple":
    """GET with a total-bytes cap and no redirect-following. Returns
    (text_or_bytes_decoded_utf8, None) or (None, error_message). Kept in
    one place so both CAL and Wiktionary inherit the same guards."""
    if _requests is None:
        return None, _NO_REQUESTS_MSG
    try:
        resp = _requests.get(url, params=params,
                             headers={"User-Agent": _USER_AGENT},
                             timeout=timeout, stream=True, allow_redirects=False)
        resp.raise_for_status()
        chunks, total = [], 0
        for chunk in resp.iter_content(65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_RESPONSE_BYTES:
                resp.close()
                return None, "response too large"
        # Both sources serve UTF-8; pin it rather than trusting requests'
        # ISO-8859-1 default for charset-less text/html (which would mojibake
        # CAL's š/ḥ/ʾ under a UI that promises the source's text verbatim).
        return b"".join(chunks).decode("utf-8", errors="replace"), None
    except Exception as exc:
        return None, exc.__class__.__name__

# --- CAL: Syriac consonant -> CAL's own ASCII search-key scheme ------------
# Codes and order read directly off CAL's own jump-grid links at
# https://cal.huc.edu/searching/fullbrowser.html (fetched 2026-07-05):
#   ) b g d h w z x T y k l m n s ( p c q r $ t
# — one code per letter, Alaph..Taw, the same order and count (22) as the
# already-verified suriyani.sedra3._UNICODE_CONSONANTS, so this table is
# built by zipping the two lists rather than retyping codepoints.
_CAL_CODES = list(")bgdhwzxTyklmns(pcqr$t")
assert len(_CAL_CODES) == len(sedra3._UNICODE_CONSONANTS) == 22

CAL_TRANSLIT: dict[str, str] = {
    chr(cp): code
    for (cp, _name), code in zip(sedra3._UNICODE_CONSONANTS, _CAL_CODES)
}

# Loose Latin equivalents, for ranking CAL's prefix-browse results only —
# never for deciding what to show or hide. Two symmetric halves, both
# collapsing down to the same plain-a-z comparison space:
#   _loose()            — CAL's own Latin display text (š, ḥ, ṭ, ʿ, ʾ, ṣ):
#                          NFD-decompose, drop combining marks and spacing
#                          modifier letters (category Lm — CAL's ʾ/ʿ), keep a-z.
#   _loose_from_cal_key() — this module's Syriac->CAL-ASCII key (already
#                          computed by to_cal()): the few codes that
#                          aren't already a plain consonant letter (the
#                          two glottal/pharyngeal codes, and heth/teth/
#                          sadhe/shin's non-letter-alike codes) get mapped
#                          to the same bare letter their Latin diacritic
#                          form would decompose to.
# A miss here just means worse ordering, never a hidden or fabricated
# result — the raw CAL text is always shown verbatim regardless.
_CAL_KEY_LOOSE_OVERRIDES = {")": "", "(": "", "x": "h", "T": "t", "c": "s", "$": "s"}


def _loose(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    kept = "".join(ch for ch in nfd
                  if not unicodedata.combining(ch) and unicodedata.category(ch) != "Lm")
    return "".join(ch for ch in kept.lower() if "a" <= ch <= "z")


def _loose_from_cal_key(cal_key: str) -> str:
    return "".join(_CAL_KEY_LOOSE_OVERRIDES.get(ch, ch.lower()) for ch in cal_key)


def to_cal(skeleton: str) -> str | None:
    """Syriac consonantal skeleton -> CAL's ASCII search-key string, or
    None if any character isn't one of the 22 Syriac consonants (a bare
    skeleton shouldn't carry seyame/vowel marks, but this defends anyway
    rather than silently mis-mapping something)."""
    out = []
    for ch in skeleton:
        code = CAL_TRANSLIT.get(ch)
        if code is None:
            return None
        out.append(code)
    return "".join(out)


@dataclass(frozen=True)
class OnlineResult:
    headword: str   # the source's own transliteration/display form, verbatim
    pos: str        # grammatical note, if the source gives one
    gloss: str      # short English gloss/definition, verbatim from the source
    url: str        # link to the live source page


# --- CAL --------------------------------------------------------------------

_CAL_ENTRY_RE = re.compile(
    r'<a href="oneentry\.php\?lemma=([^"&]+)[^"]*"[^>]*>'
    r'(?:<span class="biglem">|<span class="lem">)?'
    r'<font color="#0000A0">([^<]*)</font>.*?'
    r'<pos>([^<]*)</pos>\s*</a>.*?'
    r'<span class="gloss">([^<]*)</span>',
    re.DOTALL)


def _matches_query(headword: str, query_loose: str) -> bool:
    return any(_loose(alt.strip()) == query_loose for alt in headword.split(","))


def parse_cal_html(html_text: str, cal_key: str, limit: int = 10) -> list[OnlineResult]:
    """Pure parser, no network — takes a raw response body (real or a
    saved fixture) and the already-computed CAL search key, returns
    ranked results. Kept separate from fetch_cal() so tests can exercise
    the parsing/ranking logic against a saved real response without a
    live network dependency every run."""
    query_loose = _loose_from_cal_key(cal_key)
    seen: dict[str, OnlineResult] = {}
    for m in _CAL_ENTRY_RE.finditer(html_text):
        lemma_key, translit, pos, gloss = m.groups()
        if lemma_key in seen:
            continue
        # lemma_key arrives already percent-encoded from CAL's own hrefs,
        # except for the literal space before the homograph letter
        # ("%24lm N") — encode just that so the URL is well-formed.
        seen[lemma_key] = OnlineResult(
            headword=html.unescape(translit).strip(),
            pos=html.unescape(pos).strip(),
            gloss=html.unescape(gloss).strip(),
            url="https://cal.huc.edu/oneentry.php?lemma="
                + lemma_key.replace(" ", "%20") + "&cits=all")

    results = list(seen.values())
    results.sort(key=lambda r: not _matches_query(r.headword, query_loose))
    return results[:limit]


def fetch_cal(skeleton: str, limit: int = 10,
             timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    """Prefix-browse CAL for `skeleton`'s first 3 letters, return entries
    whose own transliteration looks like the query first (best-effort
    ranking only), then other same-prefix entries — mirroring the
    "closest headword" ethos of suriyani.lookup.suggest(), just against a
    live external source instead of the compiled store."""
    cal_key = to_cal(skeleton)
    if not cal_key:
        return [], None  # not a plain Syriac skeleton — nothing to ask CAL

    text, err = _get_capped("https://cal.huc.edu/browseSKEYheaders.php",
                            {"first3": f'"{cal_key[:3]}"'}, timeout)
    if err is not None:
        msg = err if err == _NO_REQUESTS_MSG else f"couldn't reach CAL just now ({err})"
        return [], msg
    return parse_cal_html(text, cal_key, limit=limit), None


# --- Wiktionary ---------------------------------------------------------------

_WIKT_API = "https://en.wiktionary.org/w/api.php"
_WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_GLOSS_LINE_RE = re.compile(r"(?m)^#\s*(?!\*|:)(.+)$")


def _clean_wikitext(s: str) -> str:
    # Wiktionary content is world-editable, so bound the work: one gloss
    # line can't usefully be longer than this, and the nested-template
    # strip gets a hard pass ceiling so a pathological line of deeply
    # nested braces can't spin the loop for minutes.
    s = s[:2000]
    for _ in range(25):
        new = _TEMPLATE_RE.sub("", s)
        if new == s:
            break
        s = new
    s = _WIKI_LINK_RE.sub(r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    return s.strip()


def parse_wiktionary_json(data: dict, lang_candidates: tuple[str, ...],
                          fallback_title: str) -> list[OnlineResult]:
    """Pure parser, no network — takes an already-decoded action=parse
    JSON response (real or a saved fixture) and returns results. Kept
    separate from fetch_wiktionary() for the same reason as
    parse_cal_html(): testable against a saved real response. Defends
    against valid-JSON-but-wrong-shape bodies (a captive portal or proxy
    returning null / a list / {"parse": null} with HTTP 200) — those must
    yield an empty result, never an unhandled TypeError/AttributeError."""
    if not isinstance(data, dict) or "error" in data:
        return []
    parse = data.get("parse")
    if not isinstance(parse, dict):
        return []
    wikitext = parse.get("wikitext")
    if not isinstance(wikitext, str):
        return []

    section = None
    for heading in lang_candidates:
        m = re.search(rf"(?m)^=={re.escape(heading)}==\s*$", wikitext)
        if not m:
            continue
        rest = wikitext[m.end():]
        nxt = re.search(r"(?m)^==[^=]", rest)
        section = rest[:nxt.start()] if nxt else rest
        break
    if section is None:
        return []

    glosses = [_clean_wikitext(g) for g in _GLOSS_LINE_RE.findall(section)[:6]]
    glosses = [g for g in glosses if g]
    if not glosses:
        return []

    title = parse.get("title") or fallback_title
    from urllib.parse import quote
    url = f"https://en.wiktionary.org/wiki/{quote(title)}"
    return [OnlineResult(headword=title, pos="", gloss="; ".join(glosses), url=url)]


def fetch_wiktionary(word: str, lang_candidates: tuple[str, ...],
                     timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    """MediaWiki action=parse for `word`, extract whichever of
    `lang_candidates` L2 (==Heading==) section is present, and pull its
    numbered gloss lines. A missing page or missing language section is a
    clean empty result, not an error."""
    import json as _json
    text, err = _get_capped(_WIKT_API, {
        "action": "parse", "page": word, "format": "json",
        "formatversion": 2, "prop": "wikitext"}, timeout)
    if err is not None:
        msg = err if err == _NO_REQUESTS_MSG else f"couldn't reach Wiktionary just now ({err})"
        return [], msg
    try:
        data = _json.loads(text)
    except ValueError:
        return [], "Wiktionary returned an unreadable response"
    return parse_wiktionary_json(data, lang_candidates, word), None


# --- orchestration ------------------------------------------------------------

def _run_source(fn) -> tuple[list, str | None]:
    """Belt-and-braces: any unexpected exception from a source becomes that
    source's error string, so one misbehaving source can never 500 the
    whole /online.json endpoint (each source already handles its own
    network/parse errors; this catches anything they didn't anticipate)."""
    try:
        return fn()
    except Exception as exc:
        return [], f"online source failed ({exc.__class__.__name__})"


def lookup_online(cfg, query: str) -> dict:
    """The only entry point app.py touches. `cfg` is a
    dict_registry.DictConfig; `query` is the word in its own script
    (Syriac for the Syriac dictionary, Arabic for the Arabic one) — the
    same text CAL needs transliterated and Wiktionary needs as a page
    title, so both sources are driven from one input."""
    sources: dict[str, dict] = {}
    if "cal" in cfg.online_sources:
        results, error = _run_source(lambda: fetch_cal(query))
        sources["cal"] = {"label": "CAL — Comprehensive Aramaic Lexicon",
                          "results": [asdict(r) for r in results], "error": error}
    if "wiktionary" in cfg.online_sources:
        results, error = _run_source(
            lambda: fetch_wiktionary(query, cfg.wiktionary_lang_candidates))
        sources["wiktionary"] = {"label": "Wiktionary",
                                 "results": [asdict(r) for r in results], "error": error}
    return {"query": query, "sources": sources}
