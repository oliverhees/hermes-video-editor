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

  function show(which) {
    lang = which;
    $("help-en").classList.toggle("on", lang === "en"); $("help-de").classList.toggle("on", lang === "de");
    $("help-body").scrollTop = 0;
    if (cache[lang]) { $("help-body").innerHTML = cache[lang]; return; }
    $("help-body").textContent = "…";
    fetch(V.url("/help/" + lang + ".md")).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (t) { cache[lang] = render(t); if (lang === which) $("help-body").innerHTML = cache[which]; })
      .catch(function (e) { $("help-body").textContent = "Could not load the guide: " + e.message; });
  }
  function open() { $("help").hidden = false; show(lang); }
  function close() { $("help").hidden = true; }
  $("btn-help").addEventListener("click", open);
  $("help-close").addEventListener("click", close);
  $("help-en").addEventListener("click", function () { show("en"); });
  $("help-de").addEventListener("click", function () { show("de"); });
  $("help").addEventListener("mousedown", function (e) { if (e.target === $("help")) close(); });
  $("help-body").addEventListener("click", function (e) { var a = e.target.closest && e.target.closest("a[data-ext]"); if (!a) return; e.preventDefault(); $("powered").click(); });
  window.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("help").hidden) { close(); e.stopPropagation(); } }, true);
  V.openHelp = open;
})();
