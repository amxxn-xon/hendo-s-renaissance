/* Interactive root-family graph (entry pages + root cards) — a small
   vanilla layout, no libraries.

   Two levels, mirroring the data's own structure: the root at the centre;
   each DICTIONARY FORM (lexeme) as an outlined hub around it; each
   inflected form as a filled bubble attached to its hub. Single-form
   lexemes collapse to one bubble straight off the root, and the server
   already condensed duplicate spellings, so no word appears twice.

   Motion model — "floaty, but anchored": positions are computed once by
   a short relaxation pass, then every bubble simply bobs a few pixels
   around its anchor. Nothing accumulates velocity, so nothing can drift
   away or sink. Dragging moves a bubble's anchor (a hub drags its whole
   family with it); click opens the info card. Respects
   prefers-reduced-motion (no bobbing). Progressive enhancement: without
   JS the grouped list below the graph is the page. */

(function () {
  "use strict";

  var SVGNS = "http://www.w3.org/2000/svg";

  document.addEventListener("DOMContentLoaded", function () {
    var box = document.getElementById("root-graph");
    var dataEl = document.getElementById("graph-data");
    var info = document.getElementById("root-info");
    if (!box || !dataEl) return;
    var data;
    try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }
    if (!data.lemmas || !data.lemmas.length) { box.hidden = true; return; }

    var fontClass = box.getAttribute("data-font-class") || "syr";
    var highlightId = parseInt(box.getAttribute("data-highlight") || "", 10);
    var reduced = window.matchMedia &&
                  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    var W = box.clientWidth, H = box.clientHeight;

    var svg = document.createElementNS(SVGNS, "svg");
    svg.setAttribute("class", "rg-edges");
    box.appendChild(svg);

    // --- bubble sizes: sqrt-of-frequency over ALL forms, clamped ---------
    var freqs = [];
    data.lemmas.forEach(function (L) {
      L.forms.forEach(function (f) { freqs.push(f.freq || 1); });
      if (L.self) freqs.push(L.self.freq || 1);
    });
    var fmax = Math.max.apply(null, freqs), fmin = Math.min.apply(null, freqs);
    function radius(f) {
      if (fmax === fmin) return 40;
      var t = (Math.sqrt(f) - Math.sqrt(fmin)) /
              (Math.sqrt(fmax) - Math.sqrt(fmin));
      return 28 + t * 26;                       /* 28 … 54 px */
    }

    // --- centre (the root) -------------------------------------------------
    var center = { x: W / 2, y: H / 2,
                   r: Math.min(52, Math.max(38, W / 11)) };
    var cEl = document.createElement("div");
    cEl.className = "rg-node rg-center";
    var cHw = document.createElement("span");
    cHw.className = fontClass + " rg-hw";
    cHw.textContent = data.root;
    cHw.style.fontSize = Math.round(center.r * 0.5) + "px";
    var cLab = document.createElement("span");
    cLab.className = "rg-gloss";
    cLab.textContent = "root";
    cEl.appendChild(cHw);
    cEl.appendChild(cLab);
    cEl.style.width = cEl.style.height = (center.r * 2) + "px";
    cEl.style.transform = "translate(" + (center.x - center.r) + "px," +
                                         (center.y - center.r) + "px)";
    box.appendChild(cEl);

    // --- node construction ---------------------------------------------------
    var nodes = [];

    function makeNode(cls, hwText, subText, r, parent, angle, dist, d) {
      var el = document.createElement("div");
      el.className = "rg-node " + cls;
      if (d.word_id && d.word_id === highlightId) el.className += " rg-me";
      el.setAttribute("role", "button");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", hwText + (subText ? " — " + subText : ""));
      var hw = document.createElement("span");
      hw.className = fontClass + " rg-hw";
      hw.textContent = hwText;
      hw.style.fontSize = Math.max(12, Math.round(r * 0.42)) + "px";
      el.appendChild(hw);
      if (subText && (r >= 36 || cls.indexOf("rg-lemma") >= 0)) {
        var gl = document.createElement("span");
        gl.className = "rg-gloss";
        gl.textContent = subText;
        el.appendChild(gl);
      }
      el.style.width = el.style.height = (r * 2) + "px";
      box.appendChild(el);
      var line = document.createElementNS(SVGNS, "line");
      line.setAttribute("class", "rg-edge");
      svg.appendChild(line);
      var px = parent ? parent.x : center.x;
      var py = parent ? parent.y : center.y;
      var n = { d: d, el: el, line: line, r: r, parent: parent,
                home: dist,
                x: px + Math.cos(angle) * dist,
                y: py + Math.sin(angle) * dist,
                /* anchor offset from parent/centre — the initial layout
                   pass overwrites this for build-time nodes; nodes created
                   later (hub expansion) keep this ring placement */
                ox: Math.cos(angle) * dist,
                oy: Math.sin(angle) * dist,
                bx: 0, by: 0,          /* current bob offset               */
                phase: (nodes.length * 2.399) % (2 * Math.PI),
                dragging: false };
      nodes.push(n);
      wireNode(n);
      return n;
    }

    // --- render plan: cap what's drawn so big families stay readable -----
    // The full data always lives in the list below the graph; the picture
    // shows each dictionary-form hub with its most frequent forms and a
    // "+N" bubble for the rest, plus the top standalone words. Each hub
    // family gets its own colour (rg-c0…rg-c5) so groups read as groups.
    var MAXF = parseInt(box.getAttribute("data-max-forms") || "6", 10);
    var MAXSOLO = parseInt(box.getAttribute("data-max-solo") || "16", 10);
    var listHref = box.getAttribute("data-list-href") || "#family-list";
    var FAMS = 6;

    var plan = [];
    var soloHidden = 0;
    var soloCount = 0;
    data.lemmas.forEach(function (L) {
      if (!L.self && L.forms.length === 1) {
        var isMe = highlightId && L.forms[0].word_id === highlightId;
        if (soloCount < MAXSOLO || isMe) {   // never hide the visitor's word
          plan.push({ solo: L.forms[0] });
          soloCount++;
        } else {
          soloHidden++;
        }
      } else {
        plan.push({ hub: L });
      }
    });
    if (soloHidden > 0) plan.push({ moreSolo: soloHidden });

    var nTop = plan.length;
    var famIdx = 0;
    plan.forEach(function (item, i) {
      var angle = (i / nTop) * 2 * Math.PI - Math.PI / 2;
      if (item.solo) {
        var f = item.solo;
        var r = radius(f.freq || 1);
        var n = makeNode("rg-form", f.hw, f.gloss, r, null, angle,
                         center.r + r + 60 + (i % 3) * 22, f);
        n.line.setAttribute("class", "rg-edge");
        return;
      }
      if (item.moreSolo) {
        makeNode("rg-more", "+" + item.moreSolo, "more words", 30, null,
                 angle, center.r + 80, {
          more: true, url: listHref, hw: "+" + item.moreSolo,
          gloss: "", pos: "", morph: "", freq: 0,
        });
        return;
      }
      // Dictionary-form hub — COLLAPSED by default; clicking unfolds its
      // family (and clicking again folds it back), so even a 259-word
      // root opens as a calm ring of hubs.
      var L = item.hub;
      var fam = "rg-c" + (famIdx % FAMS);
      famIdx++;
      var totalForms = L.forms.length + (L.self ? 1 : 0);
      var hubR = Math.min(48, 32 + totalForms);
      var hub = makeNode("rg-lemma " + fam, L.label,
                         totalForms + " forms ▸", hubR, null, angle,
                         center.r + hubR + 80 + (i % 2) * 26, {
        word_id: L.self ? L.self.word_id : 0,
        hw: L.label, translit: L.self ? L.self.translit : "",
        pos: "dictionary form",
        morph: L.self ? (L.self.morph || "") : "",
        gloss: L.gloss || "", freq: L.freq,
        url: L.self ? L.self.url : (L.url || (L.forms[0] && L.forms[0].url)),
        open_label: L.self ? "Open the full entry →"
                           : (L.url ? "See all its forms →" : "Open the entry →"),
      });
      hub.line.setAttribute("class", "rg-edge " + fam.replace("rg-c", "rg-e"));
      hub.L = L;
      hub.fam = fam;
      hub.expanded = false;
      hub.children = [];
      hub.formsLabel = totalForms + " forms";
      hub.glossEl = hub.el.querySelector(".rg-gloss");
    });

    // --- hub expansion ------------------------------------------------------
    function removeNode(n) {
      var i = nodes.indexOf(n);
      if (i >= 0) nodes.splice(i, 1);
      if (n.el.parentNode) n.el.parentNode.removeChild(n.el);
      if (n.line.parentNode) n.line.parentNode.removeChild(n.line);
    }

    function collapseHub(hub) {
      hub.children.forEach(removeNode);
      hub.children = [];
      hub.expanded = false;
      if (hub.glossEl) hub.glossEl.textContent = hub.formsLabel + " ▸";
    }

    function expandHub(hub) {
      var L = hub.L;
      var edgeCls = "rg-edge " + hub.fam.replace("rg-c", "rg-e");
      var shown = L.forms.slice(0, MAXF);
      if (highlightId) {                   // never hide the visitor's word
        for (var k = MAXF; k < L.forms.length; k++) {
          if (L.forms[k].word_id === highlightId) {
            shown = shown.slice(0, Math.max(0, MAXF - 1)).concat([L.forms[k]]);
            break;
          }
        }
      }
      var hiddenN = L.forms.length - shown.length;
      var count = shown.length + (hiddenN > 0 ? 1 : 0);
      shown.forEach(function (f, j) {
        var r = radius(f.freq || 1);
        var a2 = (j / count) * 2 * Math.PI - Math.PI / 2;
        var n = makeNode("rg-form " + hub.fam, f.hw, f.gloss, r, hub, a2,
                         hub.r + r + 24, f);
        n.line.setAttribute("class", edgeCls);
        hub.children.push(n);
      });
      if (hiddenN > 0) {
        var aN = ((count - 1) / count) * 2 * Math.PI - Math.PI / 2;
        var mn = makeNode("rg-more", "+" + hiddenN, "more", 26, hub, aN,
                          hub.r + 26 + 20, {
          more: true, url: L.url || listHref, hw: "+" + hiddenN,
          gloss: "", pos: "", morph: "", freq: 0,
        });
        mn.line.setAttribute("class", edgeCls);
        hub.children.push(mn);
      }
      hub.expanded = true;
      if (hub.glossEl) hub.glossEl.textContent = hub.formsLabel + " ▾";
      if (reduced) draw(0);
    }

    function toggleHub(hub) {
      if (hub.expanded) collapseHub(hub); else expandHub(hub);
    }

    // --- info panel -----------------------------------------------------------
    function select(n) {
      nodes.forEach(function (m) { m.el.classList.remove("sel"); });
      n.el.classList.add("sel");
      if (!info) return;
      while (info.firstChild) info.removeChild(info.firstChild);
      var close = document.createElement("button");
      close.type = "button";
      close.className = "ri-close";
      close.textContent = "×";
      close.setAttribute("aria-label", "Close");
      close.addEventListener("click", function () {
        info.hidden = true;
        n.el.classList.remove("sel");
      });
      var hw = document.createElement("a");
      hw.className = fontClass + " ri-hw";
      hw.href = n.d.url;
      hw.textContent = n.d.hw;
      info.appendChild(close);
      info.appendChild(hw);
      if (n.d.translit) {
        var ml = document.createElement("p");
        ml.className = "ml ri-ml";
        ml.textContent = n.d.translit;
        info.appendChild(ml);
      }
      var pos = document.createElement("p");
      pos.className = "ri-pos";
      pos.textContent = [n.d.pos, n.d.morph].filter(Boolean).join(" · ");
      if (pos.textContent) info.appendChild(pos);
      if (n.d.gloss) {
        var g = document.createElement("p");
        g.className = "ri-gloss";
        g.textContent = n.d.gloss;
        info.appendChild(g);
      }
      var f = document.createElement("p");
      f.className = "ri-freq";
      f.textContent = n.d.freq + "× in this corpus";
      info.appendChild(f);
      var open = document.createElement("a");
      open.className = "ri-open";
      open.href = n.d.url;
      open.textContent = n.d.open_label || "Open the full entry →";
      info.appendChild(open);
      info.hidden = false;
    }

    // --- one-time relaxation to find good anchors ---------------------------
    function relax() {
      var i, j, n, m, dx, dy, dist, f, overlap, px, py;
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        px = n.parent ? n.parent.x : center.x;
        py = n.parent ? n.parent.y : center.y;
        dx = n.x - px; dy = n.y - py;
        dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        f = (dist - n.home) * (n.parent ? 0.06 : 0.03);
        n.x -= f * dx / dist;
        n.y -= f * dy / dist;
        dx = n.x - center.x; dy = n.y - center.y;
        dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        overlap = center.r + n.r + 12 - dist;
        if (overlap > 0) {
          n.x += (dx / dist) * overlap * 0.5;
          n.y += (dy / dist) * overlap * 0.5;
        }
      }
      for (i = 0; i < nodes.length; i++) {
        for (j = i + 1; j < nodes.length; j++) {
          n = nodes[i]; m = nodes[j];
          dx = m.x - n.x; dy = m.y - n.y;
          dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
          overlap = n.r + m.r + 10 - dist;
          if (overlap > 0) {
            f = overlap * 0.25;
            n.x -= f * dx / dist; n.y -= f * dy / dist;
            m.x += f * dx / dist; m.y += f * dy / dist;
          }
        }
      }
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        n.x = Math.min(W - n.r, Math.max(n.r, n.x));
        n.y = Math.min(H - n.r, Math.max(n.r, n.y));
      }
    }
    for (var k = 0; k < 220; k++) relax();
    nodes.forEach(function (n) {          /* freeze anchors as offsets */
      var px = n.parent ? n.parent.x : center.x;
      var py = n.parent ? n.parent.y : center.y;
      n.ox = n.x - px; n.oy = n.y - py;
    });

    // --- render: anchor chain + gentle bob ----------------------------------
    var AMP = reduced ? 0 : 4;

    function draw(t) {
      var i, n, ax, ay;
      for (i = 0; i < nodes.length; i++) {   /* parents precede children */
        n = nodes[i];
        if (n.dragging) {
          ax = n.x; ay = n.y;                /* pointer is the anchor      */
        } else {
          ax = (n.parent ? n.parent.ax : center.x) + n.ox;
          ay = (n.parent ? n.parent.ay : center.y) + n.oy;
        }
        n.ax = ax; n.ay = ay;
        n.bx = ax + Math.sin(t / 900 + n.phase) * AMP;
        n.by = ay + Math.cos(t / 1100 + n.phase) * AMP;
        n.el.style.transform = "translate(" + (n.bx - n.r) + "px," +
                                              (n.by - n.r) + "px)";
        var px = n.parent ? n.parent.bx : center.x;
        var py = n.parent ? n.parent.by : center.y;
        n.line.setAttribute("x1", px);   n.line.setAttribute("y1", py);
        n.line.setAttribute("x2", n.bx); n.line.setAttribute("y2", n.by);
      }
    }

    if (reduced) {
      draw(0);                                   /* static, but complete   */
    } else {
      (function loop(t) {
        draw(t || 0);
        window.requestAnimationFrame(loop);
      })(0);
    }

    // The word the visitor came from: unfold its hub, ring it, open its
    // info card — even though hubs start collapsed.
    if (highlightId) {
      var owner = null;
      for (var h = 0; h < nodes.length; h++) {
        var nh = nodes[h];
        if (nh.L && nh.L.forms.some(function (f) {
          return f.word_id === highlightId;
        })) { owner = nh; break; }
      }
      if (owner) expandHub(owner);
      for (var h2 = 0; h2 < nodes.length; h2++) {
        if (nodes[h2].d.word_id === highlightId) { select(nodes[h2]); break; }
      }
    }

    // --- drag + click (wireNode is called by makeNode for every node,
    //     including children created later by hub expansion) --------------
    function wireNode(n) {
      var moved = false;
      n.el.addEventListener("pointerdown", function (ev) {
        ev.preventDefault();
        n.dragging = true; moved = false;
        n.el.setPointerCapture(ev.pointerId);
      });
      n.el.addEventListener("pointermove", function (ev) {
        if (!n.dragging) return;
        var rect = box.getBoundingClientRect();
        var nx = ev.clientX - rect.left, ny = ev.clientY - rect.top;
        nx = Math.min(W - n.r, Math.max(n.r, nx));
        ny = Math.min(H - n.r, Math.max(n.r, ny));
        if (Math.abs(nx - n.x) + Math.abs(ny - n.y) > 3) moved = true;
        n.x = nx; n.y = ny;
        if (reduced) draw(0);
      });
      n.el.addEventListener("pointerup", function () {
        if (n.dragging && moved) {            /* re-anchor where dropped  */
          var px = n.parent ? n.parent.ax : center.x;
          var py = n.parent ? n.parent.ay : center.y;
          n.ox = n.x - px; n.oy = n.y - py;
        }
        n.dragging = false;
        if (!moved) {
          if (n.d.more) { window.location.href = n.d.url; }
          else if (n.L) { toggleHub(n); select(n); }
          else { select(n); }
        }
        if (reduced) draw(0);
      });
      n.el.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          if (n.d.more) { window.location.href = n.d.url; }
          else if (n.L) { toggleHub(n); select(n); }
          else { select(n); }
        }
      });
    }

    // --- keep it fitting on resize -----------------------------------------
    window.addEventListener("resize", function () {
      var w = box.clientWidth, h = box.clientHeight;
      if (!w || !h) return;
      var sx = w / W, sy = h / H;
      W = w; H = h;
      center.x *= sx; center.y *= sy;
      cEl.style.transform = "translate(" + (center.x - center.r) + "px," +
                                           (center.y - center.r) + "px)";
      nodes.forEach(function (n) { n.ox *= sx; n.oy *= sy; });
      if (reduced) draw(0);
    });
  });
})();
