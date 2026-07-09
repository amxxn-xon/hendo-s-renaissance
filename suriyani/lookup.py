"""Query resolution for the lookup app — retrieval only, by construction.

Blueprint anchor: §6.1 step 5's separation. Everything here is a SELECT
against what compile.py stored; there is no code path that could mint a
form, a gloss, or a transliteration at query time. A query that matches
nothing produces suggestions from *stored* surfaces plus a logged miss —
the miss log is how the frequency-driven store learns what users actually
wanted (feed it back into the next compile).

Normalisation policy (small on purpose):
  * NFC, then keep only the store's own script block — Syriac
    (U+0700–074F plus seyame U+0308) or Arabic (U+0600–06FF), read from
    the store's meta — plus hyphen and spaces; everything else is noise
    from copy-paste (Latin punctuation, bidi controls, stray marks).
    Arabic bare forms additionally drop the Qur'anic annotation signs
    and tatweel and fold alef wasla, mirroring how headword_bare was
    stored.
  * If several space-separated words survive, resolve the first and say so.
  * `bare` = the consonantal skeleton (all combining marks dropped): this
    matches how headword_bare is stored, so a user can paste fully pointed
    text from a printed edition and still hit the consonantal index.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _is_syriac(ch: str) -> bool:
    return 0x0700 <= ord(ch) <= 0x074F or ch == "\u0308"


def _is_arabic(ch: str) -> bool:
    return 0x0600 <= ord(ch) <= 0x06FF


def _is_malayalam(ch: str) -> bool:
    return 0x0D00 <= ord(ch) <= 0x0D7F


def _looks_latin(s: str) -> bool:
    return any("a" <= ch.casefold() <= "z" for ch in s)


def _looks_malayalam(s: str) -> bool:
    return any(_is_malayalam(ch) for ch in s)


#: How English speakers usually type the scholarly diacritic letters that
#: actually occur in the stores' translit_lat columns (inventory checked
#: against both stores, 2026-07-08). Comparison-only \u2014 never shown.
_DIGRAPH_MAP = {
    "\u0161": "sh", "\u1e6f": "th", "\u1e0f": "dh", "\u1e35": "kh", "\u1e2b": "kh",
    "\u0121": "gh", "\u1e21": "gh", "\u1e25": "h", "\u1e6d": "t", "\u1e63": "s", "\u1e0d": "d",
    "\u1e93": "z", "\u1e07": "v",
}


def _translit_folds(s: str) -> set[str]:
    """Fold a Latin transliteration to bare a\u2013z0\u20139 comparison strings \u2014
    BOTH the academic strip (\u0161\u2192s: "slama") and the everyday English
    digraph rendering (\u0161\u2192sh: "shlama"), so a user can type either. NFD
    drops the length marks (\u0101\u2192a) and the modifier letters (\u02be, \u02bf)
    disappear with the punctuation strip. This is a *comparison*
    normalisation only \u2014 never a claim about how a word should be
    transliterated (those conventions live in the editable, still-draft
    tables/ TSVs). The stored transliteration is shown verbatim; only
    throwaway copies are folded to decide whether a typed query matches."""
    base = unicodedata.normalize("NFC", s or "").casefold()
    variants = {base, "".join(_DIGRAPH_MAP.get(ch, ch) for ch in base)}
    out = set()
    for v in variants:
        nfd = unicodedata.normalize("NFD", v)
        kept = "".join(ch for ch in nfd if not unicodedata.combining(ch))
        folded = "".join(ch for ch in kept if ch.isalnum() and ch.isascii())
        if folded:
            out.add(folded)
    return out


#: Per-script input filters. Which one applies is read from the store's
#: own meta (key 'script'), so the same resolve() serves both dictionaries.
_SCRIPT_FILTERS = {"syriac": _is_syriac, "arabic": _is_arabic}


# No headword in either source is anywhere near this long; a query past it
# is copy-paste noise or an abuse attempt. Capping the *cleaned* text at one
# choke point bounds everything downstream at once: the difflib scan in
# suggest()/_near_matches, the size of a logged miss, and the length of the
# string forwarded to the live CAL/Wiktionary fetches.
_MAX_TYPED = 64


@dataclass
class Norm:
    raw: str
    typed: str          # cleaned, first word only
    bare: str           # typed minus combining marks
    dropped_words: int  # how many extra words were ignored


def normalise(q: str, script: str = "syriac") -> Norm:
    keep = _SCRIPT_FILTERS.get(script, _is_syriac)
    nfc = unicodedata.normalize("NFC", (q or "")[:4000])
    kept = "".join(ch for ch in nfc if keep(ch) or ch in " -")
    words = kept.split()
    typed = words[0][:_MAX_TYPED] if words else ""
    bare = "".join(ch for ch in typed if not unicodedata.combining(ch))
    if script == "arabic":
        # Mirror arabiyya.buckwalter.skeleton (inlined — this module must
        # not depend on the backbone packages): drop the Qur'anic
        # annotation signs U+06D6–06ED (incl. the non-combining small
        # waw/yeh) and tatweel, fold alef wasla to plain alef.
        bare = "".join(ch for ch in bare
                       if not (0x06D6 <= ord(ch) <= 0x06ED) and ch != "\u0640")
        bare = bare.replace("\u0671", "\u0627")
    return Norm(raw=q, typed=typed, bare=bare,
                dropped_words=max(0, len(words) - 1))


@dataclass
class Resolution:
    kind: str                       # 'empty' | 'entry' | 'candidates' | 'miss'
    norm: Norm
    entries: list[sqlite3.Row] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
    matched_on: str | None = None   # 'eastern' | 'bare'


def _entries_for_ids(con: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    marks = ",".join("?" for _ in ids)
    return con.execute(
        f"SELECT * FROM entries WHERE word_id IN ({marks}) ORDER BY freq DESC",
        ids).fetchall()


def _near_matches(con: sqlite3.Connection, bare: str, limit: int = 8) -> list[dict]:
    """Closest stored surfaces to `bare` — prefix hits first, then fuzzy.

    Pure SELECT against surface_index/entries, same as everything else in
    this module: nothing here can mint a form that wasn't compiled.
    """
    # An empty skeleton (e.g. the query was a lone vowel-point/combining
    # mark with no base letter) would make the fuzzy branch's
    # `s.startswith('')` true for every stored surface — one SELECT per
    # surface and an arbitrary list of the store's most frequent words
    # presented as "near matches". That is noise, not a suggestion.
    if not bare:
        return []
    prefix_hits = [r[0] for r in con.execute(
        "SELECT DISTINCT surface FROM surface_index "
        "WHERE kind='bare' AND surface LIKE ? ORDER BY surface LIMIT ?",
        (bare.replace("%", "") + "%", limit * 3))] if bare else []

    near = list(dict.fromkeys(prefix_hits))  # de-dup, keep order
    if len(near) < limit:
        surfaces = [r[0] for r in con.execute(
            "SELECT DISTINCT surface FROM surface_index WHERE kind='bare'")]
        fuzzy = set(difflib.get_close_matches(bare, surfaces, n=limit, cutoff=0.6))
        fuzzy.update(s for s in surfaces
                     if s.startswith(bare) or (bare and bare.startswith(s)))
        for s in fuzzy:
            if s not in near:
                near.append(s)

    suggestions = []
    for s in near:
        row = con.execute(
            "SELECT e.word_id, e.headword_eastern, e.gloss_en, e.freq FROM entries e "
            "JOIN surface_index i ON i.word_id = e.word_id "
            "WHERE i.surface = ? ORDER BY e.freq DESC LIMIT 1", (s,)).fetchone()
        if row:
            suggestions.append({"surface": s, "word_id": row["word_id"],
                                "headword_eastern": row["headword_eastern"],
                                "gloss_en": row["gloss_en"], "freq": row["freq"]})
    suggestions.sort(key=lambda d: -d["freq"])
    return suggestions[:limit]


def translit_candidates(con: sqlite3.Connection, raw: str,
                        limit: int = 8) -> list[sqlite3.Row]:
    """Entries whose stored transliteration matches a typed Latin or
    Malayalam query — the "type it how it sounds" path.

    Pure retrieval: it compares the query against the `translit_lat` /
    `translit_ml` columns the *compiler* already wrote (both DRAFT/unvetted,
    like everything transliterated here), never anything minted now. Both
    tables are small, so a fold-and-scan in Python is trivial and lets us
    strip scholarly diacritics that SQL can't. Exact matches rank above
    prefix matches, then by frequency.
    """
    raw = (raw or "").strip()[:_MAX_TYPED]
    if not raw:
        return []
    latin = _translit_folds(raw) if _looks_latin(raw) else set()
    mal = unicodedata.normalize("NFC", raw) if _looks_malayalam(raw) else ""
    if not latin and not mal:
        return []

    scored: list[tuple[float, int, int]] = []      # (score, -freq, word_id)
    index = _scan_index(con)
    for word_id, folds, ml, _words, _first, freq in index:
        score = None
        if latin and folds:
            if latin & folds:
                score = 0.0                                   # exact
            elif any(len(q) >= 2 and f.startswith(q)
                     for q in latin for f in folds):
                score = 1.0                                   # prefix
            elif any(len(f) >= 3 and q.startswith(f)
                     for q in latin for f in folds):
                # The typed form EXTENDS a stored one — "baytun" when the
                # store has "baytu" (a case ending, a suffix, an -un
                # nunation the user added). Weaker than a stored prefix,
                # still clearly the same word.
                score = 1.5
        if score is None and mal and ml:
            if ml == mal:
                score = 0.0
            elif len(mal) >= 2 and ml.startswith(mal):
                score = 1.0
        if score is not None:
            scored.append((score, -freq, word_id))

    if not scored and any(len(q) >= 4 for q in latin):
        # Fuzzy pass, only when nothing better exists: "yeshua" vs
        # "yeshuw". Anchored on the first letter and pre-filtered by
        # length (without the anchor, "baytun" scored 0.83 against
        # "ayatun"/ʾāyatun — same tail, different word).
        for word_id, folds, _ml, _words, _first, freq in index:
            best = 0.0
            for q in latin:
                for f in folds:
                    if q[:1] != f[:1] or abs(len(q) - len(f)) > 3:
                        continue
                    r = difflib.SequenceMatcher(None, q, f).ratio()
                    if r > best:
                        best = r
            if best >= 0.78:
                scored.append((3.0 - best, -freq, word_id))   # 2.02 … 2.22

    scored.sort()
    return _rows_by_ids(con, [wid for _, __, wid in scored[:limit]])


_GLOSS_WORD_RE = re.compile(r"[a-z]+")

#: Per-store scan index for the Latin/Malayalam/meaning tiers. The full
#: corpora put ~20k rows in each store, and folding every transliteration
#: on every keystroke cost ~300–500 ms; folding once per process and
#: re-scanning frozensets costs a few ms. Keyed by database file path,
#: invalidated by mtime, so a rebuilt store is picked up automatically.
_SCAN_CACHE: dict[str, tuple[float, list]] = {}


def _scan_index(con: sqlite3.Connection) -> list:
    """[(word_id, translit_folds, translit_ml_nfc, gloss_words,
    first_sense_words, freq)] — precomputed comparison forms only; the
    displayed data is always re-SELECTed from the store by word_id."""
    row = con.execute("PRAGMA database_list").fetchone()
    path = row[2] or ":memory:"
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = -1.0
    hit = _SCAN_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    index = []
    for r in con.execute("SELECT word_id, translit_lat, translit_ml, "
                         "gloss_en, freq FROM entries"):
        folds = frozenset(_translit_folds(r[1])) if r[1] else frozenset()
        ml = unicodedata.normalize("NFC", r[2]) if r[2] else ""
        gl = (r[3] or "").casefold()
        words = frozenset(_GLOSS_WORD_RE.findall(gl)) if gl else frozenset()
        first = (frozenset(_GLOSS_WORD_RE.findall(gl.split(";")[0]))
                 if gl else frozenset())
        index.append((r[0], folds, ml, words, first, r[4]))
    _SCAN_CACHE[path] = (mtime, index)
    return index


def _rows_by_ids(con: sqlite3.Connection,
                 ordered_ids: list[int]) -> list[sqlite3.Row]:
    if not ordered_ids:
        return []
    marks = ",".join("?" for _ in ordered_ids)
    by_id = {r["word_id"]: r for r in con.execute(
        f"SELECT * FROM entries WHERE word_id IN ({marks})", ordered_ids)}
    return [by_id[i] for i in ordered_ids if i in by_id]


def gloss_candidates(con: sqlite3.Connection, raw: str,
                     limit: int = 8) -> list[sqlite3.Row]:
    """Entries whose stored English gloss contains the typed word — the
    "search by meaning" path ("house" → every entry glossed as house).

    Pure retrieval over the compiler's own gloss_en column, whole-word
    matches only (a substring match would make "art" hit "heart"). A
    trailing -s is forgiven so "houses" still finds "house". Entries whose
    FIRST sense matches rank above ones that mention the word later, then
    by frequency."""
    raw = (raw or "").strip().casefold()[:_MAX_TYPED]
    if not raw or not _looks_latin(raw):
        return []
    q = " ".join(_GLOSS_WORD_RE.findall(raw))
    if len(q) < 3:                     # 'a', 'to' … would flood the store
        return []
    probes = {q}
    if q.endswith("s") and len(q) > 3:
        probes.add(q[:-1])

    scored: list[tuple[int, int, int]] = []
    for word_id, _folds, _ml, words, first_sense, freq in _scan_index(con):
        if probes & words:
            scored.append((0 if probes & first_sense else 1, -freq, word_id))
    scored.sort()
    return _rows_by_ids(con, [wid for _, __, wid in scored[:limit]])


def resolve(con: sqlite3.Connection, q: str, log_misses: bool = True) -> Resolution:
    row = con.execute("SELECT value FROM meta WHERE key='script'").fetchone()
    norm = normalise(q, script=row[0] if row else "syriac")

    if norm.typed:
        # 1. Vocalised input against fetched eastern forms (only meaningful
        #    once fetch-vocalised has run; harmless no-op before that).
        if norm.typed != norm.bare:
            ids = [r[0] for r in con.execute(
                "SELECT DISTINCT word_id FROM surface_index "
                "WHERE surface = ? AND kind = 'eastern'", (norm.typed,))]
            if ids:
                return Resolution(kind="entry" if len(ids) == 1 else "candidates",
                                  norm=norm, entries=_entries_for_ids(con, ids),
                                  matched_on="eastern")

        # 2. Consonantal skeleton against the bare index.
        ids = [r[0] for r in con.execute(
            "SELECT DISTINCT word_id FROM surface_index "
            "WHERE surface = ? AND kind IN ('bare','bare_noseyame','bare_folded')",
            (norm.bare,))]
        if ids:
            return Resolution(kind="entry" if len(ids) == 1 else "candidates",
                              norm=norm, entries=_entries_for_ids(con, ids),
                              matched_on="bare")

    # 3. Transliteration fallback: a Latin ("shlama") or Malayalam query
    #    against the stored translit columns. For in-script input this is a
    #    clean no-op (the fold produces no Latin/ML probe), so it only ever
    #    *adds* a way to reach an already-compiled entry.
    tl = translit_candidates(con, q)
    if tl:
        return Resolution(kind="entry" if len(tl) == 1 else "candidates",
                          norm=norm, entries=tl, matched_on="translit")

    # 3b. English-meaning fallback: "house" → entries glossed as house.
    #     Runs only when no transliteration matched, so a romanized word
    #     that happens to be English ("men") keeps its translit reading.
    gl = gloss_candidates(con, q)
    if gl:
        return Resolution(kind="entry" if len(gl) == 1 else "candidates",
                          norm=norm, entries=gl, matched_on="gloss")

    if not norm.typed:
        return Resolution(kind="empty", norm=norm)

    # 4. Miss: near matches from stored surfaces only.
    suggestions = _near_matches(con, norm.bare, limit=8)

    if log_misses:
        # Best-effort telemetry for the next compile — it must never take
        # the response down with it. A locked or read-only store, or a
        # concurrent writer past the busy timeout, would otherwise turn the
        # very page that exists to say "this miss was logged" into a 500.
        # `q` is truncated so an abusive giant query can't bloat the store
        # (normalise already caps norm.bare; cap the raw form here too).
        try:
            con.execute("INSERT INTO misses (q, q_norm, ts) VALUES (?,?,?)",
                        (q[:200], norm.bare,
                         datetime.now(timezone.utc).isoformat(timespec="seconds")))
            con.commit()
        except sqlite3.Error:
            pass
    return Resolution(kind="miss", norm=norm, suggestions=suggestions)


def suggest(con: sqlite3.Connection, q: str, script: str, limit: int = 8) -> list[dict]:
    """Live 'as you type' candidates — closest headwords/surfaces to `q`.

    Called on every keystroke from the search box, so it must stay a plain
    SELECT (no miss-logging, no side effects): a partial word mid-typing is
    not a real query yet. Reuses the same surface_index the final resolve()
    call indexes against, so what this suggests is always something
    resolve() itself would actually find.
    """
    norm = normalise(q, script=script)
    if not norm.bare:
        # No in-script content — but the query may be a Latin or Malayalam
        # transliteration ("shlama", "ദെയ്ന"). Offer those as suggestions,
        # linking each back through its own transliteration so selecting one
        # re-resolves to the same entry.
        rows = translit_candidates(con, q, limit=limit)
        out = []
        for r in rows:
            surface = (r["translit_lat"] if _looks_latin(q) and r["translit_lat"]
                       else r["translit_ml"] or r["translit_lat"] or "")
            out.append({"surface": surface, "word_id": r["word_id"],
                        "headword_eastern": r["headword_eastern"],
                        "gloss_en": r["gloss_en"], "freq": r["freq"]})
        return out
    return _near_matches(con, norm.bare, limit=limit)


def gloss_ml_list(entry: sqlite3.Row) -> list[dict]:
    """JSON helper for templates."""
    return json.loads(entry["gloss_ml"] or "[]")
