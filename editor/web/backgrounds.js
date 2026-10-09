"use strict";
/* Background strips: a lane under the shapes where the canvas background can change over time
   (colour, gradient, picture, blur). The Picture tab edits the selected strip; with none selected it edits the project background. */
(function () {
  var V = window.VE;
  if (!V || !V.layers || !V.tracks) return;
  var S = V.S, TL = V.TL, $ = V.$, T = V.tracks, L = V.layers;

  function lookOf(b) { var o = { mode: b.mode, color: b.color }; if (b.mode === "gradient") o.color2 = b.color2; if (b.mode === "image") o.image = b.image; return o; }
  $("btn-bg-strip-add").addEventListener("click", function () {
    V.commit(function () {
      var seg = TL.newBgSeg(S.t, 3, S.bg.mode === "blur" ? { mode: "color", color: "#1b1464" } : lookOf(S.bg));      // starts like the project background (blur: a colour, so it is visible)
      seg.track = T.freeTrack("bg", seg.start, seg.dur);
      S.bgs = S.bgs.concat([seg]); V.clearSel("bg"); S.selBg = S.bgs.length - 1;
    });
    V.tab("picture");
  });
  $("btn-bg-strip-del").addEventListener("click", function () { remove(); });
  $("btn-bg-strip-all").addEventListener("click", function () {
    var b = S.bgs[S.selBg]; if (!b) return;
    V.commit(function () { S.bg = Object.assign({}, S.bg, lookOf(b)); });
  });
  function remove() {
    if (S.selBg < 0) return false; var i = S.selBg;
    V.commit(function () { S.bgs = S.bgs.filter(function (_, k) { return k !== i; }); S.selBg = -1; });
    return true;
  }
  function cssLook(b) {
    return b.mode === "gradient" ? "linear-gradient(90deg," + b.color + "," + (b.color2 || "#1b1464") + ")" : b.mode === "color" ? b.color : b.mode === "blur" ? "repeating-linear-gradient(45deg,#6b7280,#6b7280 6px,#4b5563 6px,#4b5563 12px)" : b.mode === "image" ? "#374151" : "#000";
  }
  function drawLane() {
    T.render("bg", S.bgs, { cls: "bgitem", sel: S.selBg, label: function (b) { return { blur: "Blur", black: "Black", color: "Colour", gradient: "Gradient", image: "Picture" }[b.mode] + (b.mode === "image" && b.image ? " · " + V.baseName(b.image) : ""); },
      title: function (b) { return b.mode; }, color: cssLook, start: function (b) { return b.start; }, width: function (b) { return b.dur; } });
  }
  T.drag("bg", { items: function () { return S.bgs; }, tab: "picture", after: function () { drawLane(); V.drawStage(); V.syncCanvasControls(); },
    select: function (i) { V.clearSel("bg"); S.selBg = i; },
    trim: function (it, edge, dx) { return TL.trimText(it, edge, dx); },
    replace: function (i, next) { S.bgs = S.bgs.map(function (b, k) { return k === i ? TL.cleanBgSeg(next) : b; }); } });

  var o = { drawLanes: L.drawLanes, render: L.render, deleteSelected: L.deleteSelected };
  L.drawLanes = function () { o.drawLanes(); drawLane(); };
  L.render = function () { o.render(); drawLane(); V.syncCanvasControls(); };
  L.deleteSelected = function () { return remove() || o.deleteSelected(); };
  V.renderAll();
})();
