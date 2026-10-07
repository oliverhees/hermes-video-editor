"use strict";
/* Shape layer: coloured rectangles, rounded boxes and ellipses with an opacity, shown for a time window.
   Use them as a backing under text, a bar, a frame or a colour field. Data model: timeline.js / editor/project.py. */
(function () {
  var V = window.VE;
  if (!V || !V.layers || !V.tracks) return;
  var S = V.S, TL = V.TL, $ = V.$, T = V.tracks, L = V.layers, tab = V.tab;

  function cur() { return S.selShape >= 0 ? S.shapes[S.selShape] : null; }
  function replace(i, changes) { S.shapes = S.shapes.map(function (s, k) { return k === i ? TL.cleanShape(TL.patch(s, changes)) : s; }); S.dirty = true; }
  function pct(v) { return Math.round(v * 100); }

  // ---------------------------------------------------------------- panel
  function add(preset) {
    V.commit(function () {
      var s = TL.newShape(S.t, 3); s.track = T.freeTrack("shape", s.start, s.dur);
      if (preset) s = TL.cleanShape(TL.patch(s, preset));
      S.shapes = S.shapes.concat([s]); V.clearSel("shape"); S.selShape = S.shapes.length - 1;
    });
    tab("shape");
  }
  $("btn-shape-add").addEventListener("click", function () { add(null); });
  [["sh-p-bar", { kind: "rounded", x: 0.5, y: 0.82, w: 0.8, h: 0.14, radius: 0.5, color: "#000000", op: 0.6 }],
   ["sh-p-card", { kind: "rounded", x: 0.5, y: 0.5, w: 0.8, h: 0.5, radius: 0.12, color: "#ffffff", op: 0.9 }],
   ["sh-p-circle", { kind: "ellipse", x: 0.5, y: 0.5, w: 0.4, h: 0.4 * 16 / 9, color: "#8b6cf0", op: 0.9 }],
   ["sh-p-full", { kind: "rect", x: 0.5, y: 0.5, w: 1, h: 1, color: "#000000", op: 1 }]].forEach(function (p) {
    $(p[0]).addEventListener("click", function () { if (!cur()) add(p[1]); else { V.gestureBegin(); replace(S.selShape, p[1]); V.gestureEnd(); V.renderAll(); } });
  });
  function live(changes) { var i = S.selShape; if (i < 0) return; V.gestureBegin(); replace(i, changes); drawLane(); V.drawStage(); renderPanel(true); }
  function end() { V.gestureEnd(); V.renderAll(); }
  $("sh-kind").addEventListener("change", function () { live({ kind: this.value }); end(); });
  $("sh-color").addEventListener("input", function () { live({ color: this.value }); });
  $("sh-op").addEventListener("input", function () { live({ op: +this.value / 100 }); });
  $("sh-w").addEventListener("input", function () { live({ w: +this.value / 100 }); });
  $("sh-h").addEventListener("input", function () { live({ h: +this.value / 100 }); });
  $("sh-radius").addEventListener("input", function () { live({ radius: +this.value / 100 }); });
  $("sh-start").addEventListener("input", function () { live({ start: +this.value }); });
  $("sh-dur").addEventListener("input", function () { live({ dur: +this.value }); });
  ["sh-color", "sh-op", "sh-w", "sh-h", "sh-radius", "sh-start", "sh-dur"].forEach(function (id) { $(id).addEventListener("change", end); });
  $("btn-shape-center").addEventListener("click", function () { if (S.selShape < 0) return; V.gestureBegin(); replace(S.selShape, { x: 0.5 }); end(); });
  $("btn-shape-dup").addEventListener("click", function () {
    var s = cur(); if (!s) return;
    V.commit(function () { var c = TL.cleanShape(TL.patch(s, { id: TL.uid("s"), start: s.start + s.dur })); S.shapes = S.shapes.concat([c]); V.clearSel("shape"); S.selShape = S.shapes.length - 1; });
  });
  $("btn-shape-del").addEventListener("click", function () { remove(); });
  function remove() { if (S.selShape < 0) return false; var i = S.selShape; V.commit(function () { S.shapes = S.shapes.filter(function (_, k) { return k !== i; }); S.selShape = -1; }); return true; }

  function renderPanel() {
    var s = cur(); $("sh-none").hidden = !!s; $("sh-edit").hidden = !s;
    if (!s) return;
    $("sh-kind").value = s.kind; $("sh-color").value = s.color;
    $("sh-op").value = pct(s.op); $("v-shop").textContent = pct(s.op) + "%";
    $("sh-w").value = pct(s.w); $("v-shw").textContent = pct(s.w) + "%"; $("sh-h").value = pct(s.h); $("v-shh").textContent = pct(s.h) + "%";
    $("sh-radius").value = pct(s.radius); $("v-shr").textContent = pct(s.radius) + "%"; $("sh-radius-row").hidden = s.kind !== "rounded";
    if (document.activeElement !== $("sh-start")) $("sh-start").value = s.start.toFixed(2);
    if (document.activeElement !== $("sh-dur")) $("sh-dur").value = s.dur.toFixed(2);
  }

  // ---------------------------------------------------------------- lane
  function drawLane() {
    T.render("shape", S.shapes, { cls: "sitem", sel: S.selShape, label: function (s) { return { rect: "Box", rounded: "Rounded", ellipse: "Ellipse" }[s.kind]; },
      color: function (s) { return "color-mix(in srgb," + s.color + " 55%, var(--bg))"; }, start: function (s) { return s.start; }, width: function (s) { return s.dur; } });
  }
  T.drag("shape", { items: function () { return S.shapes; }, tab: "shape", after: function () { renderPanel(); drawLane(); V.drawStage(); },
    select: function (i) { V.clearSel("shape"); S.selShape = i; },
    trim: function (it, edge, dx) { return TL.trimText(it, edge, dx); },
    replace: function (i, next) { S.shapes = S.shapes.map(function (s, k) { return k === i ? TL.cleanShape(next) : s; }); } });

  // ---------------------------------------------------------------- preview
  function drawShape(g, k, W, H, s) {
    var w = Math.max(2, Math.round(s.w * W)), h = Math.max(2, Math.round(s.h * H)), x = Math.round(s.x * W - w / 2), y = Math.round(s.y * H - h / 2);
    g.save(); g.globalAlpha = s.op; g.fillStyle = s.color; g.beginPath();
    if (s.kind === "ellipse") g.ellipse((x + w / 2) * k, (y + h / 2) * k, w / 2 * k, h / 2 * k, 0, 0, Math.PI * 2);
    else if (s.kind === "rounded") { var r = Math.max(1, s.radius * Math.min(w, h)) * k, X = x * k, Y = y * k, ww = w * k, hh = h * k; g.moveTo(X + r, Y); g.arcTo(X + ww, Y, X + ww, Y + hh, r); g.arcTo(X + ww, Y + hh, X, Y + hh, r); g.arcTo(X, Y + hh, X, Y, r); g.arcTo(X, Y, X + ww, Y, r); g.closePath(); }
    else g.rect(x * k, y * k, w * k, h * k);
    g.fill(); g.restore();
    return [x, y, w, h];
  }
  function drawStage(g, k, W, H) {
    var kc = $("stage").clientWidth / W, sel = null;
    TL.activeShapes(S.shapes, S.t).slice().sort(function (a, b) { return (a.track || 0) - (b.track || 0); }).forEach(function (s) {
      var r = drawShape(g, k, W, H, s);
      if (S.shapes[S.selShape] && S.shapes[S.selShape].id === s.id) sel = r;
      V.hits.push({ z: 10 + (s.track || 0), rect: [r[0] * kc, r[1] * kc, r[2] * kc, r[3] * kc], gizmo: "sgizmo",
        select: function () { V.clearSel("shape"); S.selShape = S.shapes.findIndex(function (x) { return x.id === s.id; }); tab("shape"); } });
    });
    var gz = $("sgizmo");
    if (!sel || V.playing()) gz.hidden = true;
    else { gz.hidden = false; gz.style.left = sel[0] * kc + "px"; gz.style.top = sel[1] * kc + "px"; gz.style.width = sel[2] * kc + "px"; gz.style.height = sel[3] * kc + "px"; }
  }
  (function () {            // drag the selected shape on the preview; the mouse wheel scales it
    var drag = null;
    $("sgizmo").addEventListener("mousedown", function (e) {
      var s = cur(); if (!s || e.button !== 0) return; var r = $("stage").getBoundingClientRect();
      drag = { x0: e.clientX, y0: e.clientY, tx: s.x, ty: s.y, w: r.width, h: r.height }; V.gestureBegin(); e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return; var nx = drag.tx + (e.clientX - drag.x0) / drag.w, ny = drag.ty + (e.clientY - drag.y0) / drag.h;
      if (Math.abs(nx - 0.5) < 0.012) nx = 0.5;
      replace(S.selShape, { x: nx, y: ny }); V.drawStage();
    });
    window.addEventListener("mouseup", function () { if (!drag) return; drag = null; V.gestureEnd(); V.renderAll(); });
    $("stage").addEventListener("wheel", function (e) {
      var s = cur(), gz = $("sgizmo"); if (!s || gz.hidden) return; var b = gz.getBoundingClientRect();
      if (e.clientX < b.left || e.clientX > b.right || e.clientY < b.top || e.clientY > b.bottom) return;
      e.preventDefault(); e.stopImmediatePropagation(); var f = Math.exp(-e.deltaY * 0.0015);
      V.gestureBegin(); replace(S.selShape, { w: s.w * f, h: s.h * f }); V.gestureEnd(); V.renderAll();
    }, { passive: false, capture: true });
  })();

  var o = { drawStage: L.drawStage, drawLanes: L.drawLanes, render: L.render, deleteSelected: L.deleteSelected };
  L.drawStage = function (g, k, W, H) { drawStage(g, k, W, H); o.drawStage(g, k, W, H); };          // shapes lie under overlays and text
  L.drawLanes = function () { o.drawLanes(); drawLane(); };
  L.render = function () { o.render(); renderPanel(); drawLane(); };
  L.deleteSelected = function () { return remove() || o.deleteSelected(); };
  V.renderAll();
})();
