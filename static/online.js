/* Live "online sources" panel — CAL + Wiktionary, fetched client-side
   after the page has already rendered. Deliberately separate from the
   compiled dictionary: this only ever reads /<slug>/online.json (see
   online_lookup.py, DECISIONS.md №28), never the compiled store's own
   routes, and a failure here never touches anything else on the page. */

(function () {
  "use strict";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function renderSource(container, source, open) {
    // One collapsed accordion per source: the summary line tells you
    // whether it's worth opening ("4 found" / "nothing found" /
    // "unavailable") without dumping every result on the page.
    var det = el("details", "online-source");
    if (open) det.open = true;
    var sum = el("summary", "online-sum");
    sum.appendChild(el("span", "online-source-title", source.label));
    var state = source.error ? "unavailable"
              : source.results.length ? source.results.length + " found"
              : "nothing found";
    sum.appendChild(el("span",
      "online-count" + (source.results.length ? "" : " online-count-empty"),
      state));
    det.appendChild(sum);

    if (source.error) {
      det.appendChild(el("p", "online-error", source.error));
    } else if (!source.results.length) {
      det.appendChild(el("p", "muted online-error", "No entry found here."));
    } else {
      var list = el("div", "online-list");
      source.results.forEach(function (r) {
        // Each result is itself collapsed: the summary line is just the
        // word and which language it's from — the meaning and the outward
        // link only unfold if the reader asks.
        var item = el("details", "online-item");
        var isum = el("summary", "online-item-sum");
        isum.appendChild(el("span", "online-headword", r.headword));
        if (r.pos) isum.appendChild(el("span", "online-lang", r.pos));
        if (r.gloss) {
          // The meaning belongs on the summary line, clipped to one line —
          // expanding is for the full text and the outward link, not for
          // discovering whether the row is worth expanding.
          var hint = el("span", "online-hint", r.gloss);
          hint.title = r.gloss;
          isum.appendChild(hint);
        }
        item.appendChild(isum);
        var body = el("div", "online-item-body");
        if (r.gloss) body.appendChild(el("p", "online-gloss-full", r.gloss));
        var a = document.createElement("a");
        a.href = r.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "online-open";
        a.textContent = "Read the full entry there →";
        body.appendChild(a);
        item.appendChild(body);
        list.appendChild(item);
      });
      det.appendChild(list);
    }
    container.appendChild(det);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var section = document.getElementById("online-section");
    var results = document.getElementById("online-results");
    if (!section || !results) return;
    var query = section.getAttribute("data-query");
    if (!query) {
      section.hidden = true;
      return;
    }
    var slug = window.DICT_SLUG || "syriac";
    fetch("/" + slug + "/online.json?q=" + encodeURIComponent(query))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        results.innerHTML = "";
        // sources is an ordered list (exact entry first, then wider nets).
        var list = data.sources || [];
        if (!list.length) {
          results.appendChild(el("p", "muted",
            "No online sources configured for this dictionary."));
          return;
        }
        // Open only the first source that actually found something; the
        // rest stay one-line summaries until asked.
        var opened = false;
        list.forEach(function (source) {
          var open = !opened && !source.error && source.results.length > 0;
          if (open) opened = true;
          renderSource(results, source, open);
        });
      })
      .catch(function () {
        results.innerHTML = "";
        results.appendChild(el("p", "online-error",
          "Couldn't load online sources right now."));
      });
  });
})();
