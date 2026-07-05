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
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _is_syriac(ch: str) -> bool:
    return 0x0700 <= ord(ch) <= 0x074F or ch == "\u0308"


def _is_arabic(ch: str) -> bool:
    return 0x0600 <= ord(ch) <= 0x06FF


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


def resolve(con: sqlite3.Connection, q: str, log_misses: bool = True) -> Resolution:
    row = con.execute("SELECT value FROM meta WHERE key='script'").fetchone()
    norm = normalise(q, script=row[0] if row else "syriac")
    if not norm.typed:
        return Resolution(kind="empty", norm=norm)

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

    # 3. Miss: near matches from stored surfaces only.
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
        return []
    return _near_matches(con, norm.bare, limit=limit)


def gloss_ml_list(entry: sqlite3.Row) -> list[dict]:
    """JSON helper for templates."""
    return json.loads(entry["gloss_ml"] or "[]")
