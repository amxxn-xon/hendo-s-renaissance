"""SEDRA IV enrichment: fetch vocalised Unicode headwords, verifiably.

Why this module exists at all: SEDRA III's flat files vocalise words in an
abstract five-vowel ASCII scheme. Producing East Syriac (Madnhāyā) pointing
from it would require editorial decisions (e.g. the zlama pšiqa/qašya
split) that the scheme simply does not encode — SEDRA IV's editors made
those decisions, and their result is served by the API as the `eastern`
field. So we fetch it; we never synthesize it. See DECISIONS.md.

Operational reality: the API at sedra.bethmardutho.org refuses automated
fetchers (robots.txt), so this step could not be run in the environment
that built this repo. It is designed to run on YOUR machine:

    pip install requests
    python compile.py fetch-vocalised            # fills the cache politely
    python compile.py fetch-vocalised --inspect  # print first raw response

Every response is cached to data/cache/sedra_api/word_<id>.json, so the
API is hit at most once per word ever, with a courtesy delay between
requests. Re-runs are free.

Defensive posture: the exact JSON field layout could not be verified from
here either (same robots block). The extractor below therefore *searches*
the response for a dict carrying a "syriac" key and only trusts it after
an alignment check — the API record's consonantal skeleton must equal
ours. On any surprise it reports and skips; it never writes a form it
could not verify.
"""

from __future__ import annotations

import json
import sqlite3
import time
import unicodedata
from datetime import date
from pathlib import Path

BASE_URL = "https://sedra.bethmardutho.org/api"
SEYAME = "\u0308"


class SedraIVClient:
    def __init__(self, cache_dir: Path, delay: float = 1.5):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self._last_hit = 0.0

    def _cache_path(self, word_id: int) -> Path:
        return self.cache_dir / f"word_{word_id}.json"

    def fetch_word(self, word_id: int) -> dict | None:
        """Cache-first fetch of /api/word/<id>.json."""
        cp = self._cache_path(word_id)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))

        import requests  # imported here so the lookup app never needs it

        wait = self.delay - (time.monotonic() - self._last_hit)
        if wait > 0:
            time.sleep(wait)
        url = f"{BASE_URL}/word/{word_id}.json"
        resp = requests.get(url, timeout=30,
                            headers={"User-Agent":
                                     "suriyani-dict/1.0 (academic; Hendo Projects)"})
        self._last_hit = time.monotonic()
        resp.raise_for_status()
        cp.write_text(resp.text, encoding="utf-8")
        return resp.json()


def _find_word_dict(obj: object) -> dict | None:
    """Depth-first search for the dict that carries the 'syriac' key.

    The response layout is unverified (see module docstring), so instead of
    assuming a path like obj["word"]["syriac"] we look for the record
    wherever it lives. First match wins.
    """
    if isinstance(obj, dict):
        if "syriac" in obj and isinstance(obj["syriac"], str):
            return obj
        for v in obj.values():
            found = _find_word_dict(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_word_dict(v)
            if found:
                return found
    return None


def _bare(s: str) -> str:
    """Consonantal skeleton for the alignment check: NFC, drop combining marks."""
    return "".join(ch for ch in unicodedata.normalize("NFC", s)
                   if not unicodedata.combining(ch))


def enrich_db(db_path: Path, cache_dir: Path, limit: int | None = None,
              delay: float = 1.5, inspect: bool = False) -> dict:
    """Fill headword_eastern / headword_western for entries still pending.

    Returns a report dict; prints nothing itself so compile.py owns the CLI
    voice. Alignment rule: API syriac (consonants only) must equal our
    headword_bare (consonants only) — SEDRA IV imported SEDRA III, so ids
    are expected to line up, but expectation is not verification.
    """
    client = SedraIVClient(cache_dir, delay=delay)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT word_id, headword_bare, provenance FROM entries "
        "WHERE headword_eastern IS NULL ORDER BY freq DESC").fetchall()
    if limit:
        rows = rows[:limit]

    report = {"tried": 0, "filled": 0, "mismatched": [], "unparsed": [],
              "errors": [], "first_raw": None}

    for row in rows:
        report["tried"] += 1
        wid = row["word_id"]
        try:
            payload = client.fetch_word(wid)
        except Exception as exc:  # network/HTTP errors: report, keep going
            report["errors"].append({"word_id": wid, "error": str(exc)})
            continue
        if inspect and report["first_raw"] is None:
            report["first_raw"] = payload

        rec = _find_word_dict(payload)
        if rec is None:
            report["unparsed"].append(wid)
            continue
        if _bare(rec["syriac"]) != _bare(row["headword_bare"]):
            report["mismatched"].append(
                {"word_id": wid, "ours": row["headword_bare"],
                 "api": rec["syriac"]})
            continue

        eastern = rec.get("eastern") or None
        western = rec.get("western") or None
        prov = json.loads(row["provenance"])
        stamp = f"SEDRA IV API /word/{wid}.json, fetched {date.today().isoformat()}"
        prov["headword_eastern"] = stamp
        prov["headword_western"] = stamp
        con.execute(
            "UPDATE entries SET headword_eastern=?, headword_western=?, "
            "provenance=? WHERE word_id=?",
            (eastern, western, json.dumps(prov), wid))
        if eastern:
            con.execute(
                "INSERT INTO surface_index (surface, word_id, kind) VALUES (?,?,?)",
                (unicodedata.normalize("NFC", eastern), wid, "eastern"))
            report["filled"] += 1
    con.commit()
    con.close()
    return report
