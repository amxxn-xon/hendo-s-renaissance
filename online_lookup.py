"""Live, read-only lookups from Wiktionary and Wikidata — a deliberate,
narrow exception to compile/lookup separation (assistance.md rule #3),
made only after explicit discussion with Ameen about the tradeoff
(DECISIONS.md №28, widened in №33). This module is NOT part of the
compiled dictionary: nothing here is stored, nothing here feeds a
compiled entry's own gloss/confidence, and the app renders its results in
a section labelled, unmissably, as live and unvetted. If a source here is
unreachable or returns nothing, the compiled dictionary's own behaviour
(suriyani.lookup.resolve()/suggest()) is completely unaffected — the two
code paths never touch; this module never imports sqlite3 and is never
given a db connection.

Sources (all keyless, documented MediaWiki/Wikibase APIs):

  Wiktionary (exact entry) — action=parse on en.wiktionary.org, pulls the
        numbered gloss lines out of the word's own L2 language section.
        The precise dictionary entry, when the page exists.
  Wiktionary (related pages) — action=query&list=search, a full-text
        search that widens the net: inflected forms, compound phrases,
        and other pages that mention the word, each linked. Looser than
        the exact entry by design — labelled as such in the UI.
  Wikidata lexemes — wbsearchentities&type=lexeme, structured lexeme
        records (form + language + part of speech). Rich for Arabic;
        Classical Syriac lexemes are still sparse on Wikidata, so the
        Syriac dictionary does not query it (see dict_registry.py).

CAL (the Comprehensive Aramaic Lexicon) was an earlier source here; it was
removed in DECISIONS №33 (its unversioned browse-CGI HTML was brittle to
parse and it covered only the Syriac side). The Wiktionary/Wikidata pair
below is keyless, JSON, documented, and serves both dictionaries.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass

from dict_registry import VERSION

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

#: Hard ceiling on how much of an external response we buffer + parse. The
#: real responses are a few KB; anything past this is a maintenance page, an
#: error dump, or a hostile body, and is not worth pinning a worker over.
#: Enforced by streaming and stopping early (see _get_capped).
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _get_capped(url: str, params: dict, timeout: float) -> "tuple":
    """GET with a total-bytes cap and no redirect-following. Returns
    (text_decoded_utf8, None) or (None, error_message). Kept in one place
    so every source inherits the same guards.

    One immediate retry on failure: user reports showed sporadic
    SSLError/ConnectionError from Wiktionary that succeed on the very next
    attempt (a dropped TLS handshake, a recycled connection) — retrying
    once turns most of those into results instead of error banners."""
    if _requests is None:
        return None, _NO_REQUESTS_MSG
    last_err = "unknown"
    for _attempt in (1, 2):
        try:
            resp = _requests.get(url, params=params,
                                 headers={"User-Agent": _USER_AGENT},
                                 timeout=timeout, stream=True,
                                 allow_redirects=False)
            resp.raise_for_status()
            chunks, total = [], 0
            for chunk in resp.iter_content(65536):
                chunks.append(chunk)
                total += len(chunk)
                if total > _MAX_RESPONSE_BYTES:
                    resp.close()
                    return None, "response too large"
            # These APIs serve UTF-8 JSON; pin it rather than trusting
            # requests' ISO-8859-1 default for a charset-less content-type.
            return b"".join(chunks).decode("utf-8", errors="replace"), None
        except Exception as exc:
            last_err = exc.__class__.__name__
            continue
    return None, f"{last_err} — a momentary network hiccup; reload to retry"


@dataclass(frozen=True)
class OnlineResult:
    headword: str   # the source's own display form, verbatim
    pos: str        # grammatical note, if the source gives one
    gloss: str      # short English gloss/definition, verbatim from the source
    url: str        # link to the live source page


def _strip_html(s: str) -> str:
    """Drop tags (Wiktionary search snippets wrap the match in <span>) and
    unescape entities. Bounded input; never executes anything."""
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


# --- Wiktionary: exact entry (action=parse) ---------------------------------

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


_L2_HEADING_RE = re.compile(r"(?m)^==([^=].*?)==\s*$")


def parse_wiktionary_json(data: dict, lang_candidates: tuple[str, ...],
                          fallback_title: str,
                          related_pattern: str | None = None) -> list[OnlineResult]:
    """Pure parser, no network — takes an already-decoded action=parse
    JSON response (real or a saved fixture) and returns one result per
    relevant language section of the page.

    A Wiktionary page for a Syriac-script or Arabic-script title usually
    carries several languages' entries: ܫܠܡܐ has Classical Syriac,
    Assyrian Neo-Aramaic, Turoyo, and Western Neo-Aramaic sections;
    سلام has Arabic plus Levantine dialect sections (verified against the
    saved fixture pages, 2026-07-08). The `lang_candidates` sections are
    the dictionary's own language (listed first); `related_pattern`, when
    given, additionally admits closely-related languages by regex over the
    L2 heading (r"Aramaic$|^Turoyo$" for Syriac, r"Arabic$" for Arabic) —
    each labelled with its own section name so a Turoyo gloss can never
    pass as Classical Syriac. Unrelated same-spelling languages (Persian,
    Urdu, Ottoman Turkish …) stay excluded.

    Defends against valid-JSON-but-wrong-shape bodies (a captive portal
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

    # Slice the page into (language, section_text) in page order.
    headings = list(_L2_HEADING_RE.finditer(wikitext))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(wikitext)
        sections.append((m.group(1).strip(), wikitext[m.end():end]))

    rel_re = re.compile(related_pattern) if related_pattern else None
    primary = [s for s in sections if s[0] in lang_candidates]
    related = [s for s in sections
               if s[0] not in lang_candidates and rel_re and rel_re.search(s[0])]

    title = parse.get("title") or fallback_title
    from urllib.parse import quote
    url = f"https://en.wiktionary.org/wiki/{quote(title)}"

    results: list[OnlineResult] = []
    for lang, section in (primary + related)[:6]:
        glosses = [_clean_wikitext(g) for g in _GLOSS_LINE_RE.findall(section)[:6]]
        glosses = [g for g in glosses if g]
        if not glosses:
            continue
        results.append(OnlineResult(headword=title, pos=lang,
                                    gloss="; ".join(glosses), url=url))
    return results


def fetch_wiktionary(word: str, lang_candidates: tuple[str, ...],
                     related_pattern: str | None = None,
                     timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    """MediaWiki action=parse for `word`; see parse_wiktionary_json for
    which language sections are kept. A missing page or missing language
    section is a clean empty result, not an error."""
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
    return parse_wiktionary_json(data, lang_candidates, word, related_pattern), None


# --- Wiktionary: related pages (action=query&list=search) -------------------

def parse_mw_search_json(data: dict, query: str, host: str,
                         drop_exact: bool = False,
                         limit: int = 8) -> list[OnlineResult]:
    """Pure parser for a MediaWiki list=search response — the same shape
    on every Wikimedia wiki, so Wiktionary and the Wikipedias share it.
    Each hit becomes a linked result whose gloss is the (HTML-stripped)
    match snippet. `drop_exact` removes the query's own page from the
    hits: on Wiktionary the exact entry is covered by the dictionary-entry
    source, so its search stays purely the wider net; on Wikipedia the
    exact article IS the prize, so it stays."""
    if not isinstance(data, dict):
        return []
    query_block = data.get("query")
    if not isinstance(query_block, dict):
        return []
    hits = query_block.get("search")
    if not isinstance(hits, list):
        return []

    out: list[OnlineResult] = []
    from urllib.parse import quote
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = hit.get("title")
        if not isinstance(title, str) or not title:
            continue
        if drop_exact and title == query:
            continue
        snippet = _strip_html(hit.get("snippet", ""))[:200]
        out.append(OnlineResult(
            headword=title, pos="",
            gloss=snippet,
            url=f"https://{host}/wiki/{quote(title)}"))
        if len(out) >= limit:
            break
    return out


def _fetch_mw_search(word: str, host: str, site_label: str,
                     drop_exact: bool,
                     timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    import json as _json
    text, err = _get_capped(f"https://{host}/w/api.php", {
        "action": "query", "list": "search", "srsearch": word,
        "format": "json", "formatversion": 2, "srlimit": 8}, timeout)
    if err is not None:
        msg = err if err == _NO_REQUESTS_MSG else f"couldn't reach {site_label} just now ({err})"
        return [], msg
    try:
        data = _json.loads(text)
    except ValueError:
        return [], f"{site_label} returned an unreadable response"
    return parse_mw_search_json(data, word, host, drop_exact=drop_exact), None


def fetch_wiktionary_search(word: str,
                            timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    return _fetch_mw_search(word, "en.wiktionary.org", "Wiktionary",
                            drop_exact=True, timeout=timeout)


def fetch_wikipedia_search(word: str, host: str,
                           timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    """Encyclopedia hits from the language's own Wikipedia — Arabic
    Wikipedia for the Arabic dictionary, Aramaic Wikipedia (arc, written
    in Syriac script) for the Syriac one. Both verified live 2026-07-09;
    same MediaWiki search API as Wiktionary."""
    return _fetch_mw_search(word, host, "Wikipedia",
                            drop_exact=False, timeout=timeout)


# --- Wiktionary: English word -> target-language translations ----------------

# Both {{trans-top|SENSE}} and {{trans-top-see|SENSE|target}} open a
# translation block — the -see variant often still carries inline entries
# (verified on the house/translations fixture, where the Arabic بيت line
# sits under a trans-top-see block).
_TRANS_TOP_RE = re.compile(r"\{\{trans-top(?:-see)?(?:\|id=[^|}]*)?\|([^}|]*)")
# {{t|...}} / {{t+|...}} on normal pages; {{tt|...}} / {{tt+|...}} on
# /translations subpages (both shapes verified against saved fixtures).
_T_TEMPLATE_RE = re.compile(r"\{\{tt?\+?\|([a-z-]+)\|([^|}]+)")
_TRANS_SUBPAGE_RE = re.compile(r"\{\{see translation subpage\|")

#: Language names for the translation codes we accept — shown as the
#: result's chip so an Assyrian Neo-Aramaic word can never pass as
#: Classical Syriac (same honesty rule as the entry-section parser).
_TRANS_LANG_NAMES = {
    "ar": "Arabic", "syc": "Classical Syriac",
    "aii": "Assyrian Neo-Aramaic", "tru": "Turoyo",
}


def parse_wiktionary_translations_json(data: dict, codes: tuple[str, ...],
                                       english_word: str,
                                       limit: int = 10) -> list[OnlineResult]:
    """Pure parser: from the ENGLISH Wiktionary page of an English word
    ("flower"), pull the translation entries whose {{t|CODE|…}} language
    code is one of `codes` (ar / syc). Each hit keeps the sense line from
    its {{trans-top|…}} block ("a colorful, conspicuous structure …"), so
    a word translating a different sense of the same English headword is
    distinguishable. Words come out verbatim from the page — never
    synthesized — and are labelled as Wiktionary content in the UI."""
    if not isinstance(data, dict) or "error" in data:
        return []
    parse = data.get("parse")
    if not isinstance(parse, dict):
        return []
    wikitext = parse.get("wikitext")
    if not isinstance(wikitext, str):
        return []

    # Only the ==English== section carries the translations of the English
    # word (the same page may hold other languages' entries below).
    m = re.search(r"(?m)^==English==\s*$", wikitext)
    if not m:
        return []
    rest = wikitext[m.end():]
    nxt = re.search(r"(?m)^==[^=]", rest)
    section = rest[:nxt.start()] if nxt else rest

    wanted = set(codes)
    out: list[OnlineResult] = []
    seen: set[str] = set()
    from urllib.parse import quote
    # Walk trans-top blocks in order; attribute each {{t|..}} inside the
    # block to that block's sense line.
    blocks = list(_TRANS_TOP_RE.finditer(section))
    for i, b in enumerate(blocks):
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(section)
        sense = _clean_wikitext(b.group(1)).strip()
        for t in _T_TEMPLATE_RE.finditer(section[b.end():end]):
            code, word = t.group(1), t.group(2).strip()
            if code not in wanted or not word or word in seen:
                continue
            seen.add(word)
            out.append(OnlineResult(
                headword=word,
                pos=_TRANS_LANG_NAMES.get(code, code),
                gloss=(f"“{english_word}” — {sense}" if sense
                       else f"a translation of “{english_word}”"),
                url=f"https://en.wiktionary.org/wiki/{quote(word)}"))
            if len(out) >= limit:
                return out
    return out


def fetch_wiktionary_translations(english_word: str, codes: tuple[str, ...],
                                  timeout: float = 6.0
                                  ) -> tuple[list[OnlineResult], str | None]:
    """Big English entries ("house") park their translation tables on a
    /translations subpage behind {{see translation subpage|…}} — when the
    main page yields nothing but carries that marker, one follow-up fetch
    of the subpage is made (and only one)."""
    import json as _json

    def get_parsed(page: str):
        text, err = _get_capped(_WIKT_API, {
            "action": "parse", "page": page, "format": "json",
            "formatversion": 2, "prop": "wikitext"}, timeout)
        if err is not None:
            msg = (err if err == _NO_REQUESTS_MSG
                   else f"couldn't reach Wiktionary just now ({err})")
            return None, msg
        try:
            return _json.loads(text), None
        except ValueError:
            return None, "Wiktionary returned an unreadable response"

    data, err = get_parsed(english_word)
    if data is None:
        return [], err
    results = parse_wiktionary_translations_json(data, codes, english_word)
    wikitext = (data.get("parse") or {}).get("wikitext") or ""
    if isinstance(wikitext, str) and _TRANS_SUBPAGE_RE.search(wikitext):
        # The subpage usually carries the PRIMARY senses (the main page
        # keeps only a stray inline table), so merge rather than fall back
        # — subpage first, de-duplicated by word.
        sub, _suberr = get_parsed(f"{english_word}/translations")
        if sub is not None:
            sub_results = parse_wiktionary_translations_json(
                sub, codes, english_word)
            seen = {r.headword for r in sub_results}
            results = sub_results + [r for r in results
                                     if r.headword not in seen]
    return results[:10], None


# --- Wikidata lexemes (wbsearchentities&type=lexeme) ------------------------

_WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def parse_wikidata_lexemes_json(data: dict, lang_labels: tuple[str, ...],
                                limit: int = 8) -> list[OnlineResult]:
    """Pure parser for a lexeme search response. Wikidata describes each
    lexeme as e.g. "Arabic, noun"; we keep only those whose language name
    (the part before the first comma) is one of `lang_labels`, so the
    Arabic dictionary doesn't surface New-Persian or Ottoman-Turkish
    lexemes that merely share the Arabic-script spelling."""
    if not isinstance(data, dict):
        return []
    hits = data.get("search")
    if not isinstance(hits, list):
        return []

    wanted = {l.lower() for l in lang_labels}
    out: list[OnlineResult] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        desc = hit.get("description")
        if not isinstance(desc, str) or not desc:
            continue
        parts = [p.strip() for p in desc.split(",")]
        lang_name = parts[0] if parts else ""
        if lang_name.lower() not in wanted:
            continue
        pos = parts[1] if len(parts) > 1 else ""
        label = hit.get("label") or hit.get("title") or ""
        url = hit.get("url") or ""
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://www.wikidata.org" + url
        out.append(OnlineResult(headword=str(label), pos=pos,
                                gloss=lang_name, url=url))
        if len(out) >= limit:
            break
    return out


def fetch_wikidata_lexemes(word: str, lang_labels: tuple[str, ...],
                           search_lang: str = "en",
                           timeout: float = 6.0) -> tuple[list[OnlineResult], str | None]:
    import json as _json
    text, err = _get_capped(_WIKIDATA_API, {
        "action": "wbsearchentities", "search": word, "language": search_lang,
        "uselang": "en", "type": "lexeme", "format": "json",
        "formatversion": 2, "limit": 15}, timeout)
    if err is not None:
        msg = err if err == _NO_REQUESTS_MSG else f"couldn't reach Wikidata just now ({err})"
        return [], msg
    try:
        data = _json.loads(text)
    except ValueError:
        return [], "Wikidata returned an unreadable response"
    return parse_wikidata_lexemes_json(data, lang_labels), None


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


#: label + fetch closure per source id. Order here is display order in the
#: UI (exact entry first, then the wider nets). Each entry maps a source id
#: to (human label, factory taking the DictConfig+query -> fetch callable).
def _sources_for(cfg, query: str) -> "list[tuple[str, str, object]]":
    catalogue = {
        "wiktionary": (
            "Wiktionary — dictionary entries",
            lambda: fetch_wiktionary(query, cfg.wiktionary_lang_candidates,
                                     cfg.wiktionary_related_pattern)),
        "wiktionary_search": (
            "Wiktionary — related pages",
            lambda: fetch_wiktionary_search(query)),
        "wikipedia": (
            cfg.wikipedia_label,
            lambda: fetch_wikipedia_search(query, cfg.wikipedia_host)),
        "wikidata": (
            "Wikidata — lexemes",
            lambda: fetch_wikidata_lexemes(query, cfg.wikidata_lang_labels)),
    }
    ordered = []
    for sid in cfg.online_sources:
        if sid in catalogue:
            label, fn = catalogue[sid]
            ordered.append((sid, label, fn))
    return ordered


def lookup_online_english(cfg, english_word: str) -> dict:
    """English-word mode: the visitor typed plain English ("flower") that
    matched nothing compiled — ask the English Wiktionary page for its
    translations into this dictionary's language. Same shape as
    lookup_online() so online.js renders it unchanged."""
    lang_name = "Syriac" if cfg.script == "syriac" else "Arabic"
    results, error = _run_source(
        lambda: fetch_wiktionary_translations(english_word,
                                              cfg.translation_codes))
    return {"query": english_word, "sources": [{
        "id": "wiktionary_translations",
        "label": f"Wiktionary — “{english_word}” in {lang_name}",
        "results": [asdict(r) for r in results],
        "error": error,
    }]}


def lookup_online(cfg, query: str) -> dict:
    """The only entry point app.py touches. `cfg` is a
    dict_registry.DictConfig; `query` is the word in its own script. Every
    source in cfg.online_sources is queried and reported independently, so
    one slow or empty source never hides the others.

    `sources` is a *list* (not a dict): display order is meaningful — the
    exact entry first, then the wider nets — and a JSON object's key order
    isn't dependable across the serializer (Flask sorts object keys), so
    the order is carried in the list itself."""
    sources: list[dict] = []
    for sid, label, fn in _sources_for(cfg, query):
        results, error = _run_source(fn)
        sources.append({"id": sid, "label": label,
                        "results": [asdict(r) for r in results],
                        "error": error})
    return {"query": query, "sources": sources}
