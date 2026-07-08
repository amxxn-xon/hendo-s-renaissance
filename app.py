#!/usr/bin/env python3
"""app.py — the online lookup machine (blueprint §6.1 step 5).

    python app.py            # http://127.0.0.1:5000

Serves both dictionaries — East Syriac→Malayalam at /syriac/ and
Arabic→Malayalam at /arabic/ — as two Blueprints built from the same
factory, registered on one Flask app with a header toggle between them.
Every route except one only reads the compiled store (SELECT-only; no
route to SEDRA, QAC, CAMeL, Olam, an LLM, or a transliterator). If a word
isn't in the store, the answer is an honest miss (logged so the next
compile can cover it).

The one exception, deliberate and narrow: `/<slug>/online.json` (see
online_lookup.py, DECISIONS.md №28) fetches live from CAL and Wiktionary
and never touches db() at all — it is a structurally separate code path,
rendered in a UI section the templates label, unmissably, as live and
unvetted. It cannot write to the store, cannot affect resolve()/suggest(),
and its failure or absence changes nothing about how the rest of this
app behaves.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from pathlib import Path

from flask import (Blueprint, Flask, abort, g, jsonify, make_response,
                    redirect, render_template, request, url_for)

import online_lookup
from dict_registry import ARABIC, DICTS, SYRIAC, VERSION, DictConfig
from suriyani.lookup import normalise, resolve, suggest

ROOT = Path(__file__).resolve().parent

app = Flask(__name__)


@app.context_processor
def _inject_version() -> dict:
    return {"version": VERSION}


# --- database handles, one per dictionary, cached per request --------------

def _dbs() -> dict:
    if "_dbs" not in g:
        g._dbs = {}
    return g._dbs


class StoreNotBuilt(Exception):
    """The compiled store for a dictionary is absent — a 503, not a 500."""


def db_for(cfg: DictConfig) -> sqlite3.Connection:
    dbs = _dbs()
    if cfg.slug not in dbs:
        # Guard before connect(): sqlite3.connect() would otherwise create a
        # stray zero-byte file for a store that was never compiled, which
        # then (a) 500s on the first query with "no such table" and (b)
        # violates the data-hygiene rule that a GET must never mint files
        # under data/. Fail as a clean, explained 503 instead.
        if not cfg.db_path.exists():
            raise StoreNotBuilt(cfg.slug)
        con = sqlite3.connect(cfg.db_path)
        con.row_factory = sqlite3.Row
        dbs[cfg.slug] = con
    return dbs[cfg.slug]


@app.teardown_appcontext
def _close_dbs(_exc) -> None:
    dbs = g.pop("_dbs", None)
    if dbs:
        for con in dbs.values():
            con.close()


# --- view-model helpers ------------------------------------------------------

def entry_vm(row: sqlite3.Row) -> dict:
    """Row → template-friendly dict (all JSON fields decoded here, not in Jinja).

    Note: `provenance` values are usually plain strings, but the Arabic
    backbone stores gloss_en's provenance as a nested dict when the gloss
    is cross_matched (see arabiyya/backbone.py) — json.loads preserves
    that structure as-is; templates branch on `is mapping`.
    """
    e = dict(row)
    e["morphology"] = json.loads(e["morphology"] or "{}")
    e["gloss_ml"] = json.loads(e["gloss_ml"] or "[]")
    e["translit_flags"] = json.loads(e["translit_flags"] or "[]")
    e["provenance"] = json.loads(e["provenance"] or "{}")
    e["confidence"] = json.loads(e["confidence"] or "{}")
    if e["example_text"]:
        e["example_tokens"] = e["example_text"].split(" ")
        e["example_hl"] = set(json.loads(e["example_hl"] or "[]"))
    else:
        e["example_tokens"], e["example_hl"] = [], set()
    # Full concordance (all verses this word appears in, capped at compile
    # time). .get() keeps the app tolerant of a store built before the
    # column existed. Each shown verse is pre-split into tokens + a
    # highlight set, mirroring the single-example fields above.
    att = json.loads(e.get("attestations") or '{"total": 0, "shown": []}')
    e["attest_total"] = att.get("total", 0)
    e["attestations"] = []
    for a in att.get("shown", []):
        e["attestations"].append({
            "ref": a.get("ref", ""),
            "tokens": (a.get("text") or "").split(" ") if a.get("text") else [],
            "hl": set(a.get("highlight") or []),
        })
    return e


def _meta(con: sqlite3.Connection) -> dict:
    return dict(con.execute("SELECT key, value FROM meta"))


def _entry_extras(con: sqlite3.Connection, e: dict) -> tuple[int, int]:
    """(frequency rank, number of forms sharing this lexeme). Rank: how many
    entries are strictly more frequent, + 1. form_count drives the entry
    page's "see all N forms" link to the lemma paradigm."""
    rank = con.execute("SELECT COUNT(*) + 1 FROM entries WHERE freq > ?",
                       (e["freq"],)).fetchone()[0]
    form_count = 0
    if e.get("lexeme_id"):
        form_count = con.execute(
            "SELECT COUNT(*) FROM entries WHERE lexeme_id = ?",
            (e["lexeme_id"],)).fetchone()[0]
    return rank, form_count


# The homepage "common words" highlight skips function words. The rule is a
# POS *category* filter, verified against both stores' actual pos
# inventories (2026-07-07): every function-word category either store uses
# — Syriac's 'particle'/'pronoun'; QAC's '… particle' subtypes, pronouns,
# prepositions, conjunctions — matches one of these substrings, and no
# content category ('noun', 'verb', 'adjective', 'numeral', 'proper noun',
# '… adverb', …) does. Deliberately not a word list: no source-language
# form is typed here, and the filtered words stay fully searchable,
# browsable, and in the root tree. Display choice only (DECISIONS №31).
_FUNCTION_POS = ("particle", "pronoun", "preposition", "conjunction")
_CONTENT_POS_WHERE = " AND ".join(
    f"pos NOT LIKE '%{p}%'" for p in _FUNCTION_POS)


# --- one blueprint per dictionary, built from the same routes ---------------

def create_dict_blueprint(cfg: DictConfig) -> Blueprint:
    bp = Blueprint(cfg.slug, __name__, url_prefix=f"/{cfg.slug}")
    keyboard = cfg.keyboard_builder()

    def db() -> sqlite3.Connection:
        return db_for(cfg)

    @bp.get("/")
    def index():
        meta = _meta(db())
        total = db().execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        n_roots = db().execute(
            "SELECT COUNT(DISTINCT root_id) FROM entries "
            "WHERE root IS NOT NULL AND root != ''").fetchone()[0]
        n_lemmas = db().execute(
            "SELECT COUNT(DISTINCT lemma) FROM entries "
            "WHERE lemma IS NOT NULL AND lemma != ''").fetchone()[0]
        samples = [entry_vm(r) for r in db().execute(
            f"SELECT * FROM entries WHERE {_CONTENT_POS_WHERE} "
            "ORDER BY freq DESC LIMIT 12")]
        # Word of the day: a date-seeded pick among the compiled content
        # words — deterministic (same word all day for everyone), pure
        # retrieval, changes at midnight UTC.
        n_content = db().execute(
            f"SELECT COUNT(*) FROM entries WHERE {_CONTENT_POS_WHERE}"
        ).fetchone()[0]
        wotd = None
        if n_content:
            offset = int(date.today().strftime("%Y%m%d")) % n_content
            row = db().execute(
                f"SELECT * FROM entries WHERE {_CONTENT_POS_WHERE} "
                "ORDER BY word_id LIMIT 1 OFFSET ?", (offset,)).fetchone()
            wotd = entry_vm(row) if row else None
        resp = make_response(render_template(
            "index.html", samples=samples, meta=meta, cfg=cfg, total=total,
            n_roots=n_roots, n_lemmas=n_lemmas, wotd=wotd))
        resp.set_cookie("last_dict", cfg.slug, max_age=60 * 60 * 24 * 365)
        return resp

    @bp.get("/roots")
    def roots():
        """The root index — one chip per root, grouped by first letter.

        Grouped by the source's own root_id, never by spelling: SEDRA
        distinguishes homographic roots, and collapsing those would assert
        an identity the source doesn't. The entries themselves live on the
        per-root family page (root_card) — this index stays scannable.
        Pure SELECT plus regrouping.
        """
        rows = db().execute(
            "SELECT root_id, root, COUNT(*) AS n, SUM(freq) AS total_freq "
            "FROM entries WHERE root IS NOT NULL AND root != '' "
            "GROUP BY root_id, root ORDER BY root, root_id").fetchall()
        # Letter buckets in codepoint order (rows arrive sorted by root, so
        # same-letter groups are already contiguous).
        letters: list[tuple[str, list]] = []
        for r in rows:
            letter = r["root"][0]
            if not letters or letters[-1][0] != letter:
                letters.append((letter, []))
            letters[-1][1].append(r)
        unrooted = db().execute(
            "SELECT COUNT(*) FROM entries "
            "WHERE root IS NULL OR root = ''").fetchone()[0]
        return render_template("roots.html", letters=letters,
                               n_roots=len(rows),
                               n_rooted=sum(r["n"] for r in rows),
                               unrooted=unrooted, meta=_meta(db()), cfg=cfg)

    @bp.get("/search")
    def search():
        q = request.args.get("q", "")
        res = resolve(db(), q)
        meta = _meta(db())
        if res.kind == "empty":
            # Distinguish a genuinely blank box (bounce home, as before)
            # from input that had content but nothing in this dictionary's
            # script survived — e.g. an Arabic word pasted into the Syriac
            # dictionary, or romanised "shlama". Show the miss page with a
            # note instead of silently redirecting, so the user isn't left
            # wondering why the page just reloaded.
            if q.strip():
                script_name = "Syriac" if cfg.script == "syriac" else "Arabic"
                return render_template(
                    "miss.html", searched=res.norm, suggestions=[],
                    meta=meta, cfg=cfg, online_query="",
                    wrong_script=script_name)
            return redirect(url_for(".index"))
        if res.kind == "entry":
            e = entry_vm(res.entries[0])
            rank, form_count = _entry_extras(db(), e)
            fam = _family(e["root_id"]) if e["root_id"] else None
            return render_template("entry.html", e=e,
                                   searched=res.norm, matched_on=res.matched_on,
                                   meta=meta, cfg=cfg, online_query=res.norm.bare,
                                   freq_rank=rank, form_count=form_count,
                                   root_graph=fam[2] if fam else None)
        if res.kind == "candidates":
            return render_template("candidates.html",
                                   entries=[entry_vm(r) for r in res.entries],
                                   searched=res.norm, matched_on=res.matched_on,
                                   meta=meta, cfg=cfg,
                                   online_query=res.norm.bare)
        return render_template("miss.html", searched=res.norm,
                               suggestions=res.suggestions, meta=meta, cfg=cfg,
                               online_query=res.norm.bare)

    @bp.get("/suggest.json")
    def suggest_json():
        q = request.args.get("q", "")
        return jsonify(suggest(db(), q, cfg.script))

    @bp.get("/online.json")
    def online_json():
        """Live CAL/Wiktionary lookup — never touches db(), by construction.
        See online_lookup.py and DECISIONS.md №28."""
        norm = normalise(request.args.get("q", ""), script=cfg.script)
        if not norm.bare:
            return jsonify({"query": "", "sources": {}})
        return jsonify(online_lookup.lookup_online(cfg, norm.bare))

    @bp.get("/browse")
    def browse():
        """Leaf through everything compiled — a plain paginated SELECT.

        The ORDER BY comes from a two-key whitelist, never from user text.
        """
        per_page = 50
        order = request.args.get("order", "freq")
        order_sql = {"freq": "freq DESC, headword_bare ASC",
                     "alpha": "headword_bare ASC, freq DESC"}.get(
                         order, "freq DESC, headword_bare ASC")
        total = db().execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        pages = max(1, (total + per_page - 1) // per_page)
        try:
            page = int(request.args.get("page", 1))
        except ValueError:
            page = 1
        page = min(max(1, page), pages)
        rows = db().execute(
            f"SELECT word_id, headword_eastern, headword_bare, translit_ml, "
            f"gloss_en, morph_summary, pos, freq FROM entries "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
            (per_page, (page - 1) * per_page)).fetchall()
        return render_template("browse.html", rows=rows, total=total,
                               page=page, pages=pages, order=order,
                               meta=_meta(db()), cfg=cfg)

    @bp.get("/random")
    def random_entry():
        """A random *compiled* entry — ORDER BY RANDOM() over the store,
        still retrieval-only: it can only ever land on something the
        compiler already vetted in."""
        row = db().execute(
            "SELECT word_id FROM entries ORDER BY RANDOM() LIMIT 1").fetchone()
        if row is None:
            abort(404)
        return redirect(url_for(".entry", word_id=row["word_id"]))

    def _family(root_id: int):
        """One root's family, grouped by the source's own lexeme_id —
        shared by the root_card page and the roots index's featured graph.
        Returns (rows, groups, graph) or None if the root isn't compiled."""
        rows = db().execute(
            "SELECT word_id, headword_eastern, headword_bare, root, lemma,"
            " lexeme_id, is_lexical_form, gloss_en, pos, freq, morph_summary,"
            " translit_ml FROM entries "
            "WHERE root_id = ? ORDER BY freq DESC", (root_id,)).fetchall()
        if not rows:
            return None

        def form_vm(r) -> dict:
            return {
                "word_id": r["word_id"],
                "hw": r["headword_eastern"] or r["headword_bare"],
                "translit": r["translit_ml"] or "",
                "gloss": (r["gloss_en"] or "").split(";")[0],
                "pos": r["pos"] or "",
                "morph": r["morph_summary"] or "",
                "freq": r["freq"],
                "url": url_for(".entry", word_id=r["word_id"]),
            }

        groups: dict = {}
        order: list[dict] = []
        for r in rows:
            key = r["lexeme_id"] if r["lexeme_id"] is not None else f"w{r['word_id']}"
            g = groups.get(key)
            if g is None:
                g = {"label": r["lemma"] or r["headword_eastern"] or r["headword_bare"],
                     "lexeme_id": r["lexeme_id"], "gloss": "", "forms": [],
                     "freq": 0, "url": (url_for(".lemma", lexeme_id=r["lexeme_id"])
                                        if r["lexeme_id"] is not None else None)}
                groups[key] = g
                order.append(g)
            g["forms"].append(form_vm(r))
            g["freq"] += r["freq"]
            if not g["gloss"] and r["gloss_en"]:
                g["gloss"] = r["gloss_en"].split(";")[0]
        order.sort(key=lambda g: -g["freq"])

        def condense(g: dict) -> dict:
            """Graph view of one lexeme group, de-duplicated: same-spelled
            forms merge into one bubble (linking to the search page, which
            disambiguates the readings), and the citation form itself is
            absorbed into the hub instead of floating as a twin bubble.
            The list view below the graph keeps every row — only the
            picture condenses."""
            merged: dict[str, dict] = {}
            forms_out: list[dict] = []
            for f in g["forms"]:
                m = merged.get(f["hw"])
                if m is None:
                    m = dict(f, readings=1)
                    merged[f["hw"]] = m
                    forms_out.append(m)
                else:
                    m["freq"] += f["freq"]
                    m["readings"] += 1
                    m["url"] = url_for(".search", q=m["hw"])
                    m["morph"] = f"{m['readings']} readings share this spelling"
            self_form = None
            if len(forms_out) > 1:
                for m in forms_out:
                    if m["hw"] == g["label"]:
                        self_form = m
                        break
                if self_form is not None:
                    forms_out = [m for m in forms_out if m is not self_form]
            return {"label": g["label"], "freq": g["freq"], "url": g["url"],
                    "gloss": g["gloss"] or (self_form or {}).get("gloss", ""),
                    "self": self_form, "forms": forms_out}

        graph = {"root": rows[0]["root"],
                 "lemmas": [condense(g) for g in order]}
        return rows, order, graph

    @bp.get("/root/<int:root_id>")
    def root_card(root_id: int):
        """One root's family — a two-level interactive graph (root →
        dictionary forms → their inflected forms) plus the same data as a
        plain grouped list. The graph is the same SELECT the list renders;
        the physics is cosmetic."""
        fam = _family(root_id)
        if fam is None:
            abort(404)
        rows, order, graph = fam
        return render_template("root_card.html", groups=order, graph=graph,
                               root=rows[0]["root"], root_id=root_id,
                               n_words=len(rows),
                               total_freq=sum(r["freq"] for r in rows),
                               meta=_meta(db()), cfg=cfg)

    @bp.get("/lemma/<int:lexeme_id>")
    def lemma(lexeme_id: int):
        """One lexeme's whole paradigm — its citation form and every
        inflected form of it the store has compiled. Pure SELECT, grouped
        by the source's own lexeme_id (never by spelling)."""
        rows = db().execute(
            "SELECT * FROM entries WHERE lexeme_id = ? "
            "ORDER BY is_lexical_form DESC, freq DESC", (lexeme_id,)).fetchall()
        if not rows:
            abort(404)
        forms = [entry_vm(r) for r in rows]
        citation = next((f for f in forms if f["is_lexical_form"]), forms[0])
        return render_template("lemma.html", forms=forms, citation=citation,
                               lexeme_id=lexeme_id, meta=_meta(db()), cfg=cfg)

    @bp.get("/entry/<int:word_id>")
    def entry(word_id: int):
        row = db().execute("SELECT * FROM entries WHERE word_id = ?",
                           (word_id,)).fetchone()
        if row is None:
            abort(404)
        e = entry_vm(row)
        rank, form_count = _entry_extras(db(), e)
        fam = _family(e["root_id"]) if e["root_id"] else None
        return render_template("entry.html", e=e, searched=None,
                               matched_on=None, meta=_meta(db()), cfg=cfg,
                               online_query=e["headword_bare"], freq_rank=rank,
                               form_count=form_count,
                               root_graph=fam[2] if fam else None)

    @bp.get("/about")
    def about():
        return render_template("about.html", meta=_meta(db()), cfg=cfg)

    @bp.get("/misses")
    def misses():
        # Grouped, not raw: the log exists to size the next compile, and
        # "which forms, how often, how recently" is the shape that answers
        # that. (SQLite guarantees the bare `q` column comes from the row
        # that supplied MAX(ts) — the most recent as-typed form.)
        rows = db().execute(
            "SELECT q_norm, q, COUNT(*) AS n, MAX(ts) AS last_ts "
            "FROM misses GROUP BY q_norm "
            "ORDER BY n DESC, last_ts DESC LIMIT 100").fetchall()
        total = db().execute("SELECT COUNT(*) FROM misses").fetchone()[0]
        return render_template("misses.html", rows=rows, total=total,
                               meta=_meta(db()), cfg=cfg)

    @bp.get("/keyboard.json")
    def keyboard_json():
        return jsonify(keyboard)

    return bp


app.register_blueprint(create_dict_blueprint(SYRIAC))
app.register_blueprint(create_dict_blueprint(ARABIC))


@app.errorhandler(StoreNotBuilt)
def _store_not_built(exc: StoreNotBuilt):
    slug = str(exc)
    cmd = ("python compile.py build" if slug == "syriac"
           else "python compile_arabic.py build")
    return render_template("store_missing.html", slug=slug, cmd=cmd), 503


@app.errorhandler(404)
def _not_found(_exc):
    # Standalone template (like store_missing.html): a 404 can fire outside
    # any blueprint, where there is no cfg/meta for base.html to render.
    return render_template("not_found.html"), 404


@app.get("/")
def root():
    cfg = DICTS.get(request.cookies.get("last_dict"), SYRIAC)
    return redirect(url_for(f"{cfg.slug}.index"))


if __name__ == "__main__":
    # Never default the Werkzeug debugger on: its interactive console is
    # remote code execution the moment the port is reachable (0.0.0.0, a
    # tunnel, a shared machine). Opt in explicitly with DICT_DEBUG=1 for
    # local development only.
    app.run(debug=bool(os.environ.get("DICT_DEBUG")))
