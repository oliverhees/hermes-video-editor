"use strict";
/* The lanes below the clips: any number of tracks per kind (scenes, text, shapes, video overlays, audio).
   A track is a row; items sit on rows by their `track` number. Higher tracks are in front and drawn higher up.
   This file only knows about rows and mouse handling; each layer module (layers.js, overlays.js, shapes.js, scenes.js)
   registers what its items look like and how a change is applied. */
(function () {
  var V = window.VE;
  if (!V) return;
  var S = V.S, TL = V.TL, $ = V.$, el = V.el;
  var TOP = 176, GAP = 4;
  var KINDS = {
    scene: { h: 26, label: "Scene", items: function () { return S.scenes; } },
    bg: { h: 26, label: "Background", items: function () { return S.bgs; } },
    text: { h: 30, label: "Text", items: function () { return S.texts; } },
    overlay: { h: 34, label: "Overlay", items: function () { return S.overlays; } },
    shape: { h: 30, label: "Shape", items: function () { return S.shapes; } },
    audio: { h: 62, label: "Audio", items: function () { return S.audios; } }
  };
  var ORDER = ["scene", "text", "overlay", "shape", "bg", "audio"];      // top to bottom: what is in front is on top
  var rows = {}, tops = {}, bottom = TOP;

  function count(kind) {
    var n = (S.tracks && S.tracks[kind]) || 1;
    KINDS[kind].items().forEach(function (it) { n = Math.max(n, (it.track || 0) + 1); });
    return Math.min(n, TL.MAX_TRACKS);
  }
  function key(kind, tr) { return kind + ":" + tr; }

  function layout() {
    var y = TOP, wanted = {};
    ORDER.forEach(function (kind) {
      var n = count(kind);
      for (var tr = n - 1; tr >= 0; tr--) {
        var k = key(kind, tr), r = rows[k];
        wanted[k] = true;
        if (!r) {
          r = rows[k] = el("div", "trow lane-" + kind); r.setAttribute("data-kind", kind); r.setAttribute("data-track", tr);
          r.appendChild(el("span", "lane-label", KINDS[kind].label + (n > 1 ? " " + (tr + 1) : "")));
          $("track").appendChild(r);
        }
        r.firstChild.textContent = KINDS[kind].label + (n > 1 ? " " + (tr + 1) : "");
        r.style.top = y + "px"; r.style.height = KINDS[kind].h + "px"; tops[k] = y;
        y += KINDS[kind].h + GAP;
      }
    });
    Object.keys(rows).forEach(function (k) { if (!wanted[k]) { rows[k].parentNode.removeChild(rows[k]); delete rows[k]; delete tops[k]; } });
    bottom = y + 6;
    $("track").style.height = bottom + "px"; $("mark-range").style.height = (bottom - 26) + "px";
    var want = Math.max(394, Math.min(bottom + 48, Math.round(window.innerHeight * 0.58)));
    if ($("app").getAttribute("data-tlh") !== String(want)) { $("app").setAttribute("data-tlh", want); $("app").style.gridTemplateRows = "48px 1fr " + want + "px"; }
    var a = audioArea(), c = $("awave");
    c.style.top = a.top + "px"; c.style.height = a.height + "px";
    syncSelect();
  }
  function audioArea() {
    var n = count("audio"), top = tops[key("audio", n - 1)] || TOP;
    return { top: top, height: n * (KINDS.audio.h + GAP) - GAP };
  }
  function rowTop(kind, tr) { return tops[key(kind, tr)] || TOP; }
  function height(kind) { return KINDS[kind].h; }
  function trackAtY(kind, clientY, fallback) {
    var best = fallback == null ? 0 : fallback, bd = 1e9;
    for (var tr = 0; tr < count(kind); tr++) {
      var r = rows[key(kind, tr)]; if (!r) continue;
      var b = r.getBoundingClientRect(), d = clientY < b.top ? b.top - clientY : clientY > b.bottom ? clientY - b.bottom : 0;
      if (d < bd) { bd = d; best = tr; }
    }
    return best;
  }

  // ---- add / remove tracks (history aware)
  function addTrack(kind) {
    if (count(kind) >= TL.MAX_TRACKS) { V.flash("That is the most tracks of this kind (" + TL.MAX_TRACKS + ")."); return; }
    V.commit(function () { S.tracks = TL.patch(S.tracks, (function () { var o = {}; o[kind] = count(kind) + 1; return o; })()); });
  }
  function removeTrack(kind) {
    var n = count(kind);
    if (n <= 1) { V.flash("There is always at least one " + KINDS[kind].label.toLowerCase() + " track."); return; }
    if (KINDS[kind].items().some(function (it) { return (it.track || 0) === n - 1; })) { V.flash("Move or delete the items on the top " + KINDS[kind].label.toLowerCase() + " track first."); return; }
    V.commit(function () { S.tracks = TL.patch(S.tracks, (function () { var o = {}; o[kind] = n - 1; return o; })()); });
  }
  function syncSelect() { /* the add/remove menu is static */ }
  $("add-track").addEventListener("change", function () {
    var v = this.value.split(":"); this.value = ""; this.blur();
    if (v[0] === "add") addTrack(v[1]); else if (v[0] === "remove") removeTrack(v[1]);
  });

  // lowest track where [start, start+dur] does not overlap an existing item (a new one is appended when all are busy)
  function freeTrack(kind, start, dur) {
    var n = count(kind), items = KINDS[kind].items();
    for (var tr = 0; tr < n; tr++) {
      var busy = items.some(function (it) { if ((it.track || 0) !== tr) return false; var w = TL.span(it); return start < w[1] - 0.001 && start + dur > w[0] + 0.001; });
      if (!busy) return tr;
    }
    var tr = Math.min(n, TL.MAX_TRACKS - 1);
    if (tr === n) { var o = {}; o[kind] = n + 1; S.tracks = TL.patch(S.tracks, o); }          // every busy track means one more row
    return tr;
  }

  // ---- items on rows
  // opt: { cls, label(it,i), title(it), start(it), width(it) (seconds), sel (index or -1), color(it) }
  function render(kind, items, opt) {
    var old = $("track").querySelectorAll('.litem[data-kind="' + kind + '"]');
    Array.prototype.slice.call(old).forEach(function (n) { n.parentNode.removeChild(n); });
    items.forEach(function (it, i) {
      var r = rows[key(kind, it.track || 0)]; if (!r) return;
      var d = el("div", "litem " + opt.cls + (i === opt.sel ? " sel" : ""), opt.label(it, i));
      d.setAttribute("data-kind", kind); d.setAttribute("data-i", i);
      d.style.left = (opt.start(it) * S.zoom) + "px"; d.style.width = Math.max(10, opt.width(it) * S.zoom - 1) + "px";
      if (opt.title) d.title = opt.title(it);
      if (opt.color) d.style.background = opt.color(it);
      var hl = el("b", "h l"), hr = el("b", "h r"); hl.setAttribute("data-edge", "left"); hr.setAttribute("data-edge", "right"); d.appendChild(hl); d.appendChild(hr);
      r.appendChild(d);
    });
  }

  // magnet: where an item being moved may snap to (seconds): the start, the playhead, clip borders and the edges of every other item
  function snapPoints(skipKind, skipIndex) {
    var pts = [0, S.t];
    TL.layout(S.clips).items.forEach(function (it) { pts.push(it.start, it.end); });
    Object.keys(KINDS).forEach(function (k) {
      KINDS[k].items().forEach(function (it, i) { if (k === skipKind && i === skipIndex) return; var w = TL.span(it); pts.push(w[0], w[1]); });
    });
    return pts;
  }
  function snapMove(kind, index, start, len) {            // returns {start, at}; `at` is the snapped time or null
    if (!S.magnet) return { start: start, at: null };
    var thr = 9 / S.zoom, best = null;
    snapPoints(kind, index).forEach(function (p) {
      [[p - start, p], [p - (start + len), p]].forEach(function (c) { var d = Math.abs(c[0]); if (d <= thr && (!best || d < best.d)) best = { d: d, shift: c[0], at: p }; });
    });
    return best ? { start: Math.max(0, start + best.shift), at: best.at } : { start: start, at: null };
  }
  function showSnap(at) { var l = $("snap-line"); if (at == null) { l.hidden = true; return; } l.hidden = false; l.style.left = (at * S.zoom) + "px"; }

  // cfg: { select(i), items(), replace(i, item), trim(item, edge, dxSeconds, i), after(), tab, onStart(i), onEnd() }
  function drag(kind, cfg) {
    var d = null;
    $("track").addEventListener("mousedown", function (e) {
      var item = e.target.closest && e.target.closest('.litem[data-kind="' + kind + '"]'); if (!item || e.button !== 0) return;
      var i = +item.getAttribute("data-i"), edge = e.target.getAttribute && e.target.getAttribute("data-edge");
      cfg.select(i);
      d = { i: i, edge: edge, x0: e.clientX, base: V.snap(), item: cfg.items()[i], moved: false, track: cfg.items()[i].track || 0 };
      if (cfg.onStart) cfg.onStart(i, d);
      cfg.after(); if (cfg.tab) V.tab(cfg.tab);
      e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!d) return; var dx = (e.clientX - d.x0) / S.zoom;
      if (Math.abs(e.clientX - d.x0) < 3 && !d.moved && trackAtY(kind, e.clientY, d.track) === d.track) return;
      d.moved = true;
      var it = d.item, next = d.edge ? cfg.trim(it, d.edge, dx, d.i) : TL.patch(it, { start: Math.max(0, it.start + dx) });
      if (!d.edge) {
        var w = TL.span(it), sn = snapMove(kind, d.i, next.start, w[1] - w[0]);
        next = TL.patch(next, { start: TL.round(sn.start), track: trackAtY(kind, e.clientY, d.track) }); showSnap(sn.at);
      }
      cfg.replace(d.i, next, d);
      S.dirty = true; layout(); cfg.after();
    });
    window.addEventListener("mouseup", function () {
      showSnap(null);
      if (!d) return; var done = d; d = null;
      if (done.moved) { S.hist.push(done.base); if (cfg.onEnd) cfg.onEnd(done); V.renderAll(); }
    });
  }

  function normalized() { var o = {}; ORDER.forEach(function (k) { o[k] = count(k); }); return o; }
  V.tracks = { normalized: normalized, layout: layout, render: render, drag: drag, rowTop: rowTop, height: height, audioArea: audioArea, count: count, add: addTrack, remove: removeTrack, freeTrack: freeTrack, trackAtY: trackAtY, KINDS: KINDS };
  window.addEventListener("resize", layout);
})();
