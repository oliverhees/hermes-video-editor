"use strict";
/* Help: shows docs/en/GUIDE.md or docs/de/GUIDE.md (the same files that are in the repo) in a dialog.
   A tiny markdown renderer for exactly what those guides use: headings, paragraphs, lists, tables, code, bold, links. Text is escaped first. */
(function () {
  var V = window.VE; if (!V) return;
  var $ = V.$, cache = {}, lang = "en";
  try { lang = (navigator.language || "en").toLowerCase().indexOf("de") === 0 ? "de" : "en"; } catch (e) { /* default */ }

  function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function inline(s) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    return s.replace(/\[([^\]]+)\]\((https:\/\/lokyy\.de\/?)\)/g, '<a href="$2" data-ext="1">$1</a>').replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");   // only the credit link stays a link
  }
  function cells(line) { return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); }); }
  function render(md) {
    var out = [], lines = md.split("\n"), i = 0;
    while (i < lines.length) {
      var l = lines[i], m;
      if (!l.trim()) { i++; continue; }
      if ((m = /^(#{1,3})\s+(.*)$/.exec(l))) { out.push("<h" + m[1].length + ">" + inline(m[2]) + "</h" + m[1].length + ">"); i++; continue; }
      if (/^\s*\|/.test(l) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
        var head = cells(l), rows = []; i += 2;
        while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
        out.push("<table><thead><tr>" + head.map(function (c) { return "<th>" + inline(c) + "</th>"; }).join("") + "</tr></thead><tbody>" +
          rows.map(function (r) { return "<tr>" + r.map(function (c) { return "<td>" + inline(c) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table>");
        continue;
      }
      if (/^\s*(\d+\.|-)\s+/.test(l)) {
        var ordered = /^\s*\d+\./.test(l), items = [];
        while (i < lines.length && /^\s*(\d+\.|-)\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*(\d+\.|-)\s+/, "")); i++; }
        out.push((ordered ? "<ol>" : "<ul>") + items.map(function (t) { return "<li>" + inline(t) + "</li>"; }).join("") + (ordered ? "</ol>" : "</ul>"));
        continue;
      }
      var para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\s*\|)/.test(lines[i]) && !/^\s*(\d+\.|-)\s+/.test(lines[i])) { para.push(lines[i]); i++; }
      out.push("<p>" + inline(para.join(" ")) + "</p>");
    }
    return out.join("\n");
  }

  var view = "guide", version = "";
  function docUrl() { return view === "guide" ? "/help/" + lang + ".md" : "/help/changelog." + lang + ".md"; }
  function show() {
    $("help-en").classList.toggle("on", lang === "en"); $("help-de").classList.toggle("on", lang === "de");
    $("help-guide").classList.toggle("on", view === "guide"); $("help-new").classList.toggle("on", view === "changelog");
    $("help-title").textContent = (view === "guide" ? "Help" : "What's new") + (version ? " \u00B7 v" + version : "");
    $("help-body").scrollTop = 0;
    var key = view + ":" + lang;
    if (cache[key]) { $("help-body").innerHTML = cache[key]; return; }
    $("help-body").textContent = "…";
    fetch(V.url(docUrl())).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (t) { cache[key] = render(t); if (key === view + ":" + lang) $("help-body").innerHTML = cache[key]; })
      .catch(function (e) { $("help-body").textContent = "Could not load the text: " + e.message; });
  }
  function seen() { $("new-dot").hidden = true; V.api("/api/seen", null, {}).catch(function () { /* not important */ }); }
  function open(which) { $("help").hidden = false; view = which === "changelog" ? "changelog" : "guide"; show(); if (view === "changelog") seen(); }
  function close() { $("help").hidden = true; }
  $("btn-help").addEventListener("click", function () { open("guide"); });
  $("btn-whatsnew").addEventListener("click", function () { open("changelog"); });
  $("help-guide").addEventListener("click", function () { view = "guide"; show(); });
  $("help-new").addEventListener("click", function () { view = "changelog"; show(); seen(); });
  $("help-close").addEventListener("click", close);
  $("help-en").addEventListener("click", function () { lang = "en"; show(); });
  $("help-de").addEventListener("click", function () { lang = "de"; show(); });
  $("help").addEventListener("mousedown", function (e) { if (e.target === $("help")) close(); });
  $("help-body").addEventListener("click", function (e) { var a = e.target.closest && e.target.closest("a[data-ext]"); if (!a) return; e.preventDefault(); $("powered").click(); });
  window.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("help").hidden) { close(); e.stopPropagation(); } }, true);
  V.openHelp = open;
  // the first start of a new version shows what is new (once); the dot stays until it was read
  V.api("/api/config").then(function (c) { version = c.version || ""; if (c.whats_new) { $("new-dot").hidden = false; open("changelog"); } }).catch(function () { /* the editor works without it */ });
})();
