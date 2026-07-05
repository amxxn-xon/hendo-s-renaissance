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
    return e


def _meta(con: sqlite3.Connection) -> dict:
    return dict(con.execute("SELECT key, value FROM meta"))


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
        samples = [entry_vm(r) for r in db().execute(
            "SELECT * FROM entries ORDER BY freq DESC LIMIT 12")]
        resp = make_response(render_template(
            "index.html", samples=samples, meta=meta, cfg=cfg, total=total))
        resp.set_cookie("last_dict", cfg.slug, max_age=60 * 60 * 24 * 365)
        return resp

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
            return render_template("entry.html", e=entry_vm(res.entries[0]),
                                   searched=res.norm, matched_on=res.matched_on,
                                   meta=meta, cfg=cfg, online_query=res.norm.bare)
        if res.kind == "candidates":
            return render_template("candidates.html",
                                   entries=[entry_vm(r) for r in res.entries],
                                   searched=res.norm, meta=meta, cfg=cfg,
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

    @bp.get("/entry/<int:word_id>")
    def entry(word_id: int):
        row = db().execute("SELECT * FROM entries WHERE word_id = ?",
                           (word_id,)).fetchone()
        if row is None:
            abort(404)
        e = entry_vm(row)
        return render_template("entry.html", e=e, searched=None,
                               matched_on=None, meta=_meta(db()), cfg=cfg,
                               online_query=e["headword_bare"])

    @bp.get("/about")
    def about():
        return render_template("about.html", meta=_meta(db()), cfg=cfg)

    @bp.get("/misses")
    def misses():
        rows = db().execute(
            "SELECT q, q_norm, ts FROM misses ORDER BY id DESC LIMIT 100").fetchall()
        return render_template("misses.html", rows=rows, meta=_meta(db()), cfg=cfg)

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
