/* On-screen input + live suggestions for the search field.
   Three independent layers, each degrading gracefully:
   1. A reference tap-keyboard built from /<slug>/keyboard.json — the
      server generates that JSON from the Unicode character database, so
      every key label is the official character name. Works offline, always.
   2. KeymanWeb's east_syriac_qwerty (a real typing layout), attached to
      the input only on the Syriac side, if the Keyman CDN loaded.
   3. A "closest headword" suggest dropdown, fed by /<slug>/suggest.json —
      a plain SELECT against the compiled store (see suriyani/lookup.py
      suggest()), never a live generator. Progressive enhancement: search
      still works by hitting Enter if this never loads. */

(function () {
  "use strict";

  var SLUG = window.DICT_SLUG || "syriac";

  function insertAtCaret(input, text) {
    input.focus();
    var s = input.selectionStart, e = input.selectionEnd;
    if (s === null || s === undefined) { input.value += text; return; }
    input.setRangeText(text, s, e, "end");
  }

  function buildRow(container, keys, input) {
    var row = document.createElement("div");
    row.className = "kbd-row";
    keys.forEach(function (k) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "key";
      // Combining marks render on a dotted circle for the label only.
      b.textContent = (k.n.indexOf("POINT") >= 0 || k.n.indexOf("DIAERESIS") >= 0 ||
                       k.n.indexOf("LINE") >= 0 || k.n.indexOf("QUSHSHAYA") >= 0 ||
                       k.n.indexOf("RUKKAKHA") >= 0 || k.n.indexOf("FEMININE DOT") >= 0 ||
                       k.n.indexOf("MARK") >= 0)
                      ? "◌" + k.c : k.c;
      b.title = k.n;
      b.addEventListener("click", function () { insertAtCaret(input, k.c); });
      row.appendChild(b);
    });
    container.appendChild(row);
  }

  function status(msg) {
    var el = document.getElementById("kmw-status");
    if (el) el.textContent = msg;
  }

  function tryKeyman() {
    if (SLUG !== "syriac") return;   // only a verified keyboard id for Syriac
    if (window.__kmwFailed || !window.keyman) {
      status("Keyman CDN not reachable — the tap-keyboard below works offline.");
      return;
    }
    window.keyman.init({ attachType: "auto" })
      .then(function () { return window.keyman.addKeyboards("east_syriac_qwerty@syr"); })
      .then(function () { status("Keyman east_syriac_qwerty attached to the search box; the tap-keyboard below also works."); })
      .catch(function () { status("Keyman failed to initialise — using the tap-keyboard."); });
  }

  // --- live "closest headword" suggestions ----------------------------------

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, ctx = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms);
    };
  }

  function initSuggest(input, box) {
    var items = [], selected = -1;

    function render(results) {
      box.innerHTML = "";
      items = results;
      selected = -1;
      if (!results.length) { box.hidden = true; return; }
      results.forEach(function (r, i) {
        var a = document.createElement("a");
        a.className = "suggest-item";
        a.href = input.form.action + "?q=" + encodeURIComponent(r.surface);
        var hw = document.createElement("span");
        hw.className = input.className.split(" ")[0] + " s-hw";
        hw.textContent = r.headword_eastern || r.surface;
        var gloss = document.createElement("span");
        gloss.className = "gloss";
        gloss.textContent = r.gloss_en || "";
        a.appendChild(hw);
        a.appendChild(gloss);
        a.addEventListener("mouseenter", function () { mark(i); });
        box.appendChild(a);
      });
      box.hidden = false;
    }

    function mark(i) {
      var els = box.querySelectorAll(".suggest-item");
      els.forEach(function (el) { el.classList.remove("sel"); });
      if (i >= 0 && i < els.length) { els[i].classList.add("sel"); selected = i; }
    }

    var fetchSuggestions = debounce(function () {
      var q = input.value.trim();
      if (!q) { box.hidden = true; return; }
      fetch("/" + SLUG + "/suggest.json?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(render)
        .catch(function () { box.hidden = true; });
    }, 180);

    input.addEventListener("input", fetchSuggestions);
    input.addEventListener("keydown", function (ev) {
      if (box.hidden) return;
      if (ev.key === "ArrowDown") { ev.preventDefault(); mark(Math.min(selected + 1, items.length - 1)); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); mark(Math.max(selected - 1, 0)); }
      else if (ev.key === "Enter" && selected >= 0) {
        ev.preventDefault();
        window.location = box.querySelectorAll(".suggest-item")[selected].href;
      } else if (ev.key === "Escape") { box.hidden = true; }
    });
    input.addEventListener("blur", function () {
      setTimeout(function () { box.hidden = true; }, 150); // let a click register first
    });
    input.addEventListener("focus", function () {
      if (items.length) box.hidden = false;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var input = document.getElementById("q");
    var kbd = document.getElementById("kbd");
    var suggestBox = document.getElementById("suggest");
    if (kbd && input) {
      fetch("/" + SLUG + "/keyboard.json").then(function (r) { return r.json(); })
        .then(function (data) {
          buildRow(kbd, data.letters, input);
          buildRow(kbd, data.points, input);
        })
        .catch(function () { kbd.textContent = "keyboard unavailable"; });
    }
    if (input) tryKeyman();
    if (input && suggestBox) initSuggest(input, suggestBox);
  });
})();
