"use strict";
/* Edit tools above the timeline: split, trim to the playhead, clone, delete, undo/redo, magnet.
   They work on whatever is selected: a clip, or one item of a layer (text, shape, video on top, sound, background strip). */
(function () {
  var V = window.VE;
  if (!V || !V.tracks) return;
  var S = V.S, TL = V.TL, $ = V.$;
  var MIN = 0.1;
  var KINDS = {
    text: { list: "texts", sel: "selText", dur: true }, shape: { list: "shapes", sel: "selShape", dur: true },
    bg: { list: "bgs", sel: "selBg", dur: true }, scene: { list: "scenes", sel: "selScene", dur: true },
    overlay: { list: "overlays", sel: "selOv", dur: false }, audio: { list: "audios", sel: "selAudio", dur: false }
  };

  function selected() {                                   // the selected layer item, or null (then the clip is meant)
    for (var k in KINDS) { var i = S[KINDS[k].sel]; if (i >= 0 && S[KINDS[k].list][i]) return { kind: k, i: i, item: S[KINDS[k].list][i], def: KINDS[k] }; }
    return null;
  }
  function window_(it, def) { return def.dur ? [it.start, it.start + it.dur] : [it.start, it.start + (it.out - it["in"])]; }
  function setItem(sel, next, extra) {
    var list = S[sel.def.list].map(function (x, k) { return k === sel.i ? next : x; });
    if (extra) list = list.concat([extra]);
    S[sel.def.list] = list; S.dirty = true;
  }
  function clean(kind, it) {
    return kind === "text" ? TL.cleanText(it) : kind === "shape" ? TL.cleanShape(it) : kind === "bg" ? TL.cleanBgSeg(it) : kind === "scene" ? TL.cleanScene(it)
      : kind === "overlay" ? TL.cleanOverlay(it) : TL.cleanAudio(it);
  }

  // ---------------------------------------------------------------- layer items
  function splitItem(sel, t) {
    var w = window_(sel.item, sel.def);
    if (sel.kind === "scene") { V.flash("A scene cannot be split. Use Copy scene, or Ungroup."); return; }
    if (t - w[0] < MIN || w[1] - t < MIN) { V.flash("Move the playhead inside the selected item to split it."); return; }
    V.commit(function () {
      var it = sel.item, a, b;
      if (sel.def.dur) { a = TL.patch(it, { dur: TL.round(t - it.start) }); b = TL.patch(it, { id: TL.uid(it.id.charAt(0)), start: TL.round(t), dur: TL.round(w[1] - t) }); }
      else { var cut = TL.round(it["in"] + (t - it.start)); a = TL.patch(it, { out: cut }); b = TL.patch(it, { id: TL.uid(it.id.charAt(0)), "in": cut, start: TL.round(t) }); }
      if (a.fo != null) { a = TL.patch(a, { fo: 0 }); }                                  // a fade-out belongs to the end, a fade-in to the start
      if (b.fi != null) { b = TL.patch(b, { fi: 0 }); }
      setItem(sel, clean(sel.kind, a), clean(sel.kind, b));
      S[sel.def.sel] = S[sel.def.list].length - 1;                                        // the right piece stays selected
    });
  }
  function trimItem(sel, t, side) {
    var w = window_(sel.item, sel.def);
    if (t <= w[0] + 0.001 || t >= w[1] - 0.001) { V.flash("Move the playhead inside the selected item to trim it."); return; }
    if (side === "start" ? w[1] - t < MIN : t - w[0] < MIN) { V.flash("That would leave less than " + MIN + " s."); return; }
    V.commit(function () {
      var it = sel.item, n;
      if (side === "start") n = sel.def.dur ? { start: TL.round(t), dur: TL.round(w[1] - t) } : { "in": TL.round(it["in"] + (t - it.start)), start: TL.round(t) };
      else n = sel.def.dur ? { dur: TL.round(t - it.start) } : { out: TL.round(it["in"] + (t - it.start)) };
      setItem(sel, clean(sel.kind, TL.patch(it, n)));
    });
  }
  function cloneItem(sel) {
    if (sel.kind === "scene") { $("btn-scene-dup").click(); return; }
    var w = window_(sel.item, sel.def), len = w[1] - w[0];
    V.commit(function () {
      var c = TL.patch(sel.item, { id: TL.uid(sel.item.id.charAt(0)), start: TL.round(w[1]) });          // right behind the original
      if (V.tracks.KINDS[sel.kind]) c.track = V.tracks.freeTrack(sel.kind, c.start, len);
      S[sel.def.list] = S[sel.def.list].concat([clean(sel.kind, c)]); S[sel.def.sel] = S[sel.def.list].length - 1; S.dirty = true;
    });
  }

  // ---------------------------------------------------------------- clips (the main track closes gaps by itself)
  function clipTrim(side) {
    var hit = TL.at(S.clips, S.t);
    if (!hit) { V.flash("Move the playhead inside a clip."); return; }
    var r = TL.split(S.clips, S.t, TL.uid("c"));
    if (!r.changed) { V.flash("The playhead is at the very edge of the clip."); return; }
    V.ops.edit(function () { S.sel = r.index - 1; return TL.removeIndex(r.clips, side === "start" ? r.index - 1 : r.index); });          // the piece that stays is selected
  }

  // ---------------------------------------------------------------- the buttons
  function split() { var s = selected(); if (s) splitItem(s, S.t); else V.ops.split(); }
  function trimStart() { var s = selected(); if (s) trimItem(s, S.t, "start"); else clipTrim("start"); }
  function trimEnd() { var s = selected(); if (s) trimItem(s, S.t, "end"); else clipTrim("end"); }
  function clone() { var s = selected(); if (s) cloneItem(s); else V.ops.clone(); }
  function remove() { V.ops.remove(); }

  $("tb-split").addEventListener("click", split);
  $("tb-trim-start").addEventListener("click", trimStart);
  $("tb-trim-end").addEventListener("click", trimEnd);
  $("tb-clone").addEventListener("click", clone);
  $("tb-delete").addEventListener("click", remove);
  $("tb-undo").addEventListener("click", V.ops.undo);
  $("tb-redo").addEventListener("click", V.ops.redo);
  $("tb-magnet").addEventListener("click", function () { S.magnet = !S.magnet; sync(); });
  function sync() {
    $("tb-magnet").classList.toggle("on", !!S.magnet);
    $("tb-undo").disabled = !S.hist.canUndo(); $("tb-redo").disabled = !S.hist.canRedo();
    var any = S.clips.length > 0 || !!selected();
    ["tb-split", "tb-trim-start", "tb-trim-end", "tb-clone", "tb-delete"].forEach(function (id) { $(id).disabled = !any; });
  }
  var L = V.layers, prev = L.render;
  L.render = function () { prev(); sync(); };
  S.magnet = true; sync();

  // keys: Q / W trim the start / end to the playhead, Ctrl+D clones; S splits whatever is selected
  window.addEventListener("keydown", function (e) {
    if (/INPUT|SELECT|TEXTAREA/.test(e.target.tagName || "") && e.target.type !== "range" && e.target.type !== "checkbox") return;
    if (!$("modal").hidden || !$("help").hidden) return;
    var k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey;
    if (mod && k === "d") { e.preventDefault(); e.stopImmediatePropagation(); clone(); }
    else if (!mod && k === "q") { e.preventDefault(); trimStart(); }
    else if (!mod && k === "w") { e.preventDefault(); trimEnd(); }
    else if (!mod && k === "s") { e.preventDefault(); e.stopImmediatePropagation(); split(); }
  }, true);

  V.tools = { split: split, trimStart: trimStart, trimEnd: trimEnd, clone: clone, selected: selected };
  V.renderAll();
})();
