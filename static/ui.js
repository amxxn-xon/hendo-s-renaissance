/* Small page-level niceties, all client-side and optional — the pages
   work identically if this file never loads:
   1. "/" focuses the search box (the reference-work convention).
   2. "Copy headword" button on entry pages — copies the compiled
      headword's Unicode as stored, nothing derived or transformed.
   3. Light/dark toggle — stores the choice in localStorage; a tiny
      inline script in <head> re-applies it before first paint. */

(function () {
  "use strict";

  function currentTheme() {
    var forced = document.documentElement.getAttribute("data-theme");
    if (forced) return forced;
    return (window.matchMedia &&
            window.matchMedia("(prefers-color-scheme: dark)").matches)
           ? "dark" : "light";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  });

  // "⛶ Full screen" buttons on root-family graphs: fullscreen the graph's
  // wrapper (graph + info card together). The graph script listens for
  // window resize, so nudge it when fullscreen toggles.
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".graph-fs").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var section = btn.closest("section, article, main") || document;
        var wrap = section.querySelector(".root-graph-wrap");
        if (!wrap) return;
        if (document.fullscreenElement) {
          document.exitFullscreen && document.exitFullscreen();
        } else if (wrap.requestFullscreen) {
          wrap.requestFullscreen().catch(function () {});
        }
      });
    });
  });
  document.addEventListener("fullscreenchange", function () {
    window.dispatchEvent(new Event("resize"));
  });

  // The PWA/offline layer was removed (site will be hosted normally) —
  // clean up any worker a previous visit may have installed, so nobody
  // is stuck on stale cached pages.
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then(function (regs) { regs.forEach(function (r) { r.unregister(); }); })
      .catch(function () {});
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "/" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var t = ev.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    var q = document.getElementById("q");
    if (q) { ev.preventDefault(); q.focus(); q.select(); }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var btns = document.querySelectorAll(".copy-hw");
    if (!btns.length) return;
    // The clipboard API needs a secure context (https or localhost);
    // where it's absent the button would be a dead control — remove it.
    if (!navigator.clipboard) {
      btns.forEach(function (b) { b.remove(); });
      return;
    }
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(btn.getAttribute("data-copy") || "")
          .then(function () {
            var old = btn.textContent;
            btn.textContent = "Copied";
            btn.classList.add("copied");
            setTimeout(function () {
              btn.textContent = old;
              btn.classList.remove("copied");
            }, 1400);
          })
          .catch(function () {});
      });
    });
  });
})();
