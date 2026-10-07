"use strict";
/* Scenes: a named time range that bundles texts, shapes, video overlays and audio items.
   Moving a scene on its lane moves everything in it. Deleting a scene keeps the items (or removes them too, on request).
   Scenes only exist in the editor and the project file; the export does not need them. */
(function () {
  var V = window.VE;
  if (!V || !V.layers || !V.tracks) return;
  var S = V.S, TL = V.TL, $ = V.$, T = V.tracks, L = V.layers, tab = V.tab;
  var LISTS = ["texts", "shapes", "overlays", "audios"];

  function cur() { return S.selScene >= 0 ? S.scenes[S.selScene] : null; }
  function replace(i, changes) { S.scenes = S.scenes.map(function (s, k) { return k === i ? TL.cleanScene(TL.patch(s, changes)) : s; }); S.dirty = true; }
  function inScene(sc, item) { return sc.items.indexOf(item.id) >= 0; }

  // every item that STARTS inside [a, b)
  function itemsStartingIn(a, b) {
    var ids = [];
    LISTS.forEach(function (name) { S[name].forEach(function (it) { if (it.start >= a - 0.001 && it.start < b - 0.001) ids.push(it.id); }); });
    return ids;
  }
  $("btn-scene-add").addEventListener("click", function () {
    var m = S.mark, a, b;
    if (m && m.a != null && m.b != null && m.b - m.a > 0.1) { a = m.a; b = m.b; }                // the marked range, else from the playhead
    else { a = S.t; b = S.t + 5; }
    var ids = itemsStartingIn(a, b);
    if (!ids.length && !(m && m.a != null)) { V.flash("Nothing starts in the next 5 s. Mark a range (I and O) or move the playhead to the first item of the scene."); return; }
    V.commit(function () {
      var sc = TL.newScene(a, b - a, "Scene " + (S.scenes.length + 1), ids); sc.track = T.freeTrack("scene", sc.start, sc.dur);
      S.scenes = S.scenes.concat([sc]); V.clearSel("scene"); S.selScene = S.scenes.length - 1;
    });
    tab("scene");
  });
  $("sc-name").addEventListener("input", function () { V.gestureBegin(); replace(S.selScene, { name: this.value }); drawLane(); });
  $("sc-name").addEventListener("change", function () { V.gestureEnd(); V.renderAll(); });
  $("sc-color").addEventListener("input", function () { V.gestureBegin(); replace(S.selScene, { color: this.value }); drawLane(); });
  $("sc-color").addEventListener("change", function () { V.gestureEnd(); V.renderAll(); });
  $("btn-scene-dup").addEventListener("click", function () {
    var sc = cur(); if (!sc) return;
    V.commit(function () {                                                                         // copy the scene with copies of its items right after it
      var delta = sc.dur, map = {}, copies = [];
      LISTS.forEach(function (name) {
        S[name] = S[name].concat(S[name].filter(function (it) { return inScene(sc, it); }).map(function (it) {
          var c = TL.patch(it, { id: TL.uid(it.id.charAt(0)), start: TL.round(it.start + delta) }); map[it.id] = c.id; copies.push(c.id); return c;
        }));
      });
      var ns = TL.cleanScene(TL.patch(sc, { id: TL.uid("sc"), name: sc.name + " copy", start: TL.round(sc.start + delta), items: copies }));
      S.scenes = S.scenes.concat([ns]); V.clearSel("scene"); S.selScene = S.scenes.length - 1;
    });
  });
  $("btn-scene-ungroup").addEventListener("click", function () { removeScene(false); });
  $("btn-scene-del").addEventListener("click", function () { removeScene(true); });
  function removeScene(withItems) {
    var sc = cur(); if (!sc) return false;
    V.commit(function () {
      if (withItems) LISTS.forEach(function (name) { S[name] = S[name].filter(function (it) { return !inScene(sc, it); }); });
      S.scenes = S.scenes.filter(function (x) { return x.id !== sc.id; }); S.selScene = -1;
      V.clearSel("none");
    });
    return true;
  }
  function renderPanel(light) {
    var sc = cur(); $("sc-none").hidden = !!sc; $("sc-edit").hidden = !sc;
    if (!sc) return;
    if (!light || document.activeElement !== $("sc-name")) $("sc-name").value = sc.name;
    $("sc-color").value = sc.color;
    var n = 0; LISTS.forEach(function (name) { n += S[name].filter(function (it) { return inScene(sc, it); }).length; });
    $("sc-info").textContent = n + " item" + (n === 1 ? "" : "s") + " · " + V.fmt(sc.start) + " → " + V.fmt(sc.start + sc.dur);
  }

  function drawLane() {
    T.render("scene", S.scenes, { cls: "scitem", sel: S.selScene, label: function (sc) { return sc.name; }, title: function (sc) { return sc.name; },
      color: function (sc) { return "color-mix(in srgb," + sc.color + " 60%, var(--bg))"; }, start: function (sc) { return sc.start; }, width: function (sc) { return sc.dur; } });
  }
  T.drag("scene", { items: function () { return S.scenes; }, tab: "scene", after: function () { renderPanel(true); drawLane(); V.drawStage(); },
    select: function (i) { V.clearSel("scene"); S.selScene = i; },
    trim: function (it, edge, dx) { return TL.trimText(it, edge, dx); },                           // only the extent changes, not the items
    replace: function (i, next, d) {
      var sc = TL.cleanScene(next), delta = sc.start - d.item.start;
      S.scenes = S.scenes.map(function (x, k) { return k === i ? sc : x; });
      if (!d.edge) LISTS.forEach(function (name) {                                                // everything bundled moves along (from the state before the drag)
        S[name] = (d.base[name] || []).map(function (it) { return inScene(d.item, it) ? TL.shiftItem(it, delta) : it; });
      });
    } });

  var o = { drawLanes: L.drawLanes, render: L.render, deleteSelected: L.deleteSelected };
  L.drawLanes = function () { o.drawLanes(); drawLane(); };
  L.render = function () { o.render(); renderPanel(); drawLane(); };
  L.deleteSelected = function () { return o.deleteSelected() || (S.selScene >= 0 && removeScene(false)); };
  V.renderAll();
})();
