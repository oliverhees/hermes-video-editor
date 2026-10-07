"use strict";
/* Overlay track (picture-in-picture): a second video above the main picture, with its own lane, tab and preview.
   Plugs into the hooks of layers.js (window.VE.layers). Data model and limits: timeline.js / editor/project.py. */
(function () {
  var V = window.VE;
  if (!V || !V.layers) return;
  var S = V.S, TL = V.TL, $ = V.$, el = V.el, clamp = V.clamp, L = V.layers;

  var tab = V.tab, T = V.tracks;
  function cur() { return S.selOv >= 0 ? S.overlays[S.selOv] : null; }
  function clearOthers() { V.clearSel("overlay"); }
  function replace(i, changes) { S.overlays = S.overlays.map(function (o, k) { return k === i ? TL.cleanOverlay(TL.patch(o, changes)) : o; }); S.dirty = true; }
  function setTf(i, tf) { var o = S.overlays[i]; replace(i, { tf: TL.cleanTf(TL.patch(o.tf, tf)) }); }

  // ---------------------------------------------------------------- panel
  $("btn-ov-add").addEventListener("click", function () {
    V.openDialog({ kind: "media", title: "Add a video on top", done: function (path) {
      V.flash("Reading " + V.baseName(path) + "…");
      V.ensureAsset(path).then(function (a) {
        if (!a.hasVideo) { V.flash(a.name + " has no picture."); return; }
        V.commit(function () { var no = TL.newOverlay(a.id, a.dur, S.t); no.track = T.freeTrack("overlay", no.start, TL.audioDur(no)); S.overlays = S.overlays.concat([no]); clearOthers(); S.selOv = S.overlays.length - 1; });
      }).catch(function (e) { V.flash("Could not add the video: " + e.message); });
    } });
  });
  function live(changes) { var i = S.selOv; if (i < 0) return; V.gestureBegin(); replace(i, changes); drawLane(); V.drawStage(); renderPanel(true); }
  function liveTf(tf) { var i = S.selOv; if (i < 0) return; V.gestureBegin(); setTf(i, tf); V.drawStage(); renderPanel(true); }
  function end() { V.gestureEnd(); V.renderAll(); }
  $("ov-s").addEventListener("input", function () { liveTf({ s: +this.value / 100 }); });
  $("ov-op").addEventListener("input", function () { live({ op: +this.value / 100 }); });
  $("ov-vol").addEventListener("input", function () { live({ vol: +this.value }); });
  $("ov-start").addEventListener("input", function () { live({ start: +this.value }); });
  $("ov-sound").addEventListener("change", function () { live({ sound: this.checked }); end(); });
  ["ov-s", "ov-op", "ov-vol", "ov-start"].forEach(function (id) { $(id).addEventListener("change", end); });
  [["ov-c-tl", { x: -0.27, y: -0.27 }], ["ov-c-tr", { x: 0.27, y: -0.27 }], ["ov-c-bl", { x: -0.27, y: 0.27 }], ["ov-c-br", { x: 0.27, y: 0.27 }], ["ov-c-mid", { x: 0, y: 0 }]].forEach(function (p) {
    $(p[0]).addEventListener("click", function () { if (S.selOv < 0) return; V.gestureBegin(); setTf(S.selOv, p[1]); end(); });
  });
  $("ov-c-full").addEventListener("click", function () { if (S.selOv < 0) return; V.gestureBegin(); setTf(S.selOv, { s: 1, x: 0, y: 0 }); end(); });
  $("btn-ov-del").addEventListener("click", function () { remove(); });
  function remove() {
    if (S.selOv < 0) return false; var i = S.selOv, o = S.overlays[i];
    V.commit(function () { S.overlays = S.overlays.filter(function (_, k) { return k !== i; }); S.selOv = -1; });
    if (pool[o.id]) { try { pool[o.id].pause(); } catch (e) { /* ignore */ } delete pool[o.id]; }
    return true;
  }
  function renderPanel(light) {
    var o = cur(); $("ov-none").hidden = !!o; $("ov-edit").hidden = !o;
    if (!o) return;
    var asset = V.assetFor(o.asset);
    $("ov-name").textContent = (asset ? asset.name : "?") + "  " + V.fmt(o["in"]) + " → " + V.fmt(o.out);
    $("ov-s").value = Math.round(o.tf.s * 100); $("v-ovs").textContent = Math.round(o.tf.s * 100) + "%";
    $("ov-op").value = Math.round(o.op * 100); $("v-ovop").textContent = Math.round(o.op * 100) + "%";
    $("ov-sound").checked = o.sound; $("ov-vol").value = o.vol; $("v-ovvol").textContent = Math.round(o.vol) + " dB"; $("ov-vol").disabled = !o.sound;
    if (document.activeElement !== $("ov-start")) $("ov-start").value = o.start.toFixed(2);
  }

  // ---------------------------------------------------------------- lane
  function drawLane() {
    T.render("overlay", S.overlays, { cls: "oitem", sel: S.selOv, label: function (o) { var a = V.assetFor(o.asset); return a ? a.name : "?"; },
      title: function (o) { var a = V.assetFor(o.asset); return a ? a.name : ""; }, start: function (o) { return o.start; }, width: function (o) { return TL.audioDur(o); } });
  }
  T.drag("overlay", { items: function () { return S.overlays; }, tab: "overlay", after: function () { renderPanel(true); drawLane(); V.drawStage(); },
    select: function (i) { clearOthers(); S.selOv = i; },
    trim: function (it, edge, dx) { var asset = V.assetFor(it.asset); return TL.trimAudio(it, edge, dx, asset && asset.dur); },
    replace: function (i, next) { S.overlays = S.overlays.map(function (o, k) { return k === i ? TL.cleanOverlay(next) : o; }); } });

  // ---------------------------------------------------------------- preview: one hidden <video> per overlay
  var pool = {};
  function node(o, asset) {
    var n = pool[o.id];
    if (!n) { n = pool[o.id] = document.createElement("video"); n.playsInline = true; n.preload = "auto"; n.muted = true; n.addEventListener("seeked", function () { V.drawStage(); }); n.src = asset.src; }
    n.muted = !o.sound; n.volume = clamp(Math.pow(10, o.vol / 20), 0, 1);
    return n;
  }
  function active() { return TL.activeOverlays(S.overlays, S.t); }
  function drawStage(g, k, W, H) {
    var hit = null;
    var kc = $("stage").clientWidth / W;
    active().slice().sort(function (a, b) { return (a.track || 0) - (b.track || 0); }).forEach(function (o) {
      var asset = V.assetFor(o.asset); if (!asset || !asset.src || !asset.info || !asset.info.video) return;
      var n = node(o, asset), want = o["in"] + (S.t - o.start);
      if (!V.playing() && Math.abs(n.currentTime - want) > 0.04) { try { n.currentTime = want; } catch (e) { /* not ready */ } }
      var r = TL.fgRect(asset.info.video.display_width, asset.info.video.display_height, W, H, o.tf);
      if (n.readyState >= 2 && n.videoWidth) { g.globalAlpha = o.op; g.drawImage(n, r[0] * k, r[1] * k, r[2] * k, r[3] * k); g.globalAlpha = 1; }
      if (S.overlays[S.selOv] && S.overlays[S.selOv].id === o.id) hit = r;
      V.hits.push({ z: 20 + (o.track || 0), rect: [r[0] * kc, r[1] * kc, r[2] * kc, r[3] * kc], gizmo: "ogizmo",
        select: function () { clearOthers(); S.selOv = S.overlays.findIndex(function (x) { return x.id === o.id; }); tab("overlay"); } });
    });
    var gz = $("ogizmo");
    if (!hit || V.playing()) gz.hidden = true;
    else { var kc = $("stage").clientWidth / W; gz.hidden = false; gz.style.left = hit[0] * kc + "px"; gz.style.top = hit[1] * kc + "px"; gz.style.width = hit[2] * kc + "px"; gz.style.height = hit[3] * kc + "px"; }
  }
  (function () {            // drag the selected overlay on the preview, mouse wheel = size
    var drag = null;
    $("ogizmo").addEventListener("mousedown", function (e) {
      var o = cur(); if (!o || e.button !== 0) return; var r = $("stage").getBoundingClientRect();
      drag = { x0: e.clientX, y0: e.clientY, tx: o.tf.x, ty: o.tf.y, w: r.width, h: r.height }; V.gestureBegin(); e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return; setTf(S.selOv, { x: drag.tx + (e.clientX - drag.x0) / drag.w, y: drag.ty + (e.clientY - drag.y0) / drag.h }); V.drawStage();
    });
    window.addEventListener("mouseup", function () { if (!drag) return; drag = null; V.gestureEnd(); V.renderAll(); });
    $("stage").addEventListener("wheel", function (e) {
      var o = cur(), gz = $("ogizmo"); if (!o || gz.hidden) return; var b = gz.getBoundingClientRect();
      if (e.clientX < b.left || e.clientX > b.right || e.clientY < b.top || e.clientY > b.bottom) return;
      e.preventDefault(); e.stopImmediatePropagation(); V.gestureBegin(); setTf(S.selOv, { s: o.tf.s * Math.exp(-e.deltaY * 0.0015) }); V.gestureEnd(); V.renderAll();
    }, { passive: false, capture: true });
  })();
  function tick() {
    active().forEach(function (o) {
      var asset = V.assetFor(o.asset); if (!asset || !asset.src) return;
      var n = node(o, asset), want = o["in"] + (S.t - o.start);
      if (n.paused) { try { n.currentTime = want; } catch (e) { /* not ready */ } var pr = n.play(); if (pr && pr.catch) pr.catch(function () { /* blocked until the next click */ }); }
      else if (Math.abs(n.currentTime - want) > 0.35) n.currentTime = want;
    });
    S.overlays.forEach(function (o) { var n = pool[o.id]; if (n && !n.paused && !(S.t >= o.start && S.t < TL.audioEnd(o))) n.pause(); });
  }
  function stop() { Object.keys(pool).forEach(function (id) { try { pool[id].pause(); } catch (e) { /* ignore */ } }); }

  // ---------------------------------------------------------------- hook into layers.js
  var o = { drawStage: L.drawStage, drawLanes: L.drawLanes, render: L.render, tick: L.tick, stop: L.stop, deleteSelected: L.deleteSelected };
  L.drawStage = function (g, k, W, H) { drawStage(g, k, W, H); o.drawStage(g, k, W, H); };     // overlays sit under the text
  L.drawLanes = function () { o.drawLanes(); drawLane(); };
  L.render = function () { o.render(); renderPanel(); drawLane(); };
  L.tick = function () { o.tick(); tick(); };
  L.stop = function () { o.stop(); stop(); };
  L.deleteSelected = function () { return remove() || o.deleteSelected(); };
  V.renderAll();
})();
