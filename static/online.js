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

  function renderSource(container, source) {
    var box = el("div", "online-source");
    box.appendChild(el("h3", "online-source-title", source.label));
    if (source.error) {
      box.appendChild(el("p", "online-error", source.error));
    } else if (!source.results.length) {
      box.appendChild(el("p", "muted", "No entry found."));
    } else {
      var list = el("ul", "online-list");
      source.results.forEach(function (r) {
        var li = el("li", "online-item");
        var a = document.createElement("a");
        a.href = r.url;
        a.target = "_blank";
        a.rel = "noopener";
        a.className = "online-headword";
        a.textContent = r.headword;
        li.appendChild(a);
        if (r.pos) li.appendChild(el("span", "online-pos", " " + r.pos));
        li.appendChild(el("span", "online-gloss", " " + r.gloss));
        list.appendChild(li);
      });
      box.appendChild(list);
    }
    container.appendChild(box);
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
        var keys = Object.keys(data.sources || {});
        if (!keys.length) {
          results.appendChild(el("p", "muted",
            "No online sources configured for this dictionary."));
          return;
        }
        keys.forEach(function (k) { renderSource(results, data.sources[k]); });
      })
      .catch(function () {
        results.innerHTML = "";
        results.appendChild(el("p", "online-error",
          "Couldn't load online sources right now."));
      });
  });
})();
