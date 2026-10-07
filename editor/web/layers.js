"use strict";
/* Text layer and audio track: lanes on the timeline, the Text tab, the audio controls and their preview.
   Works on the shared state of app.js (window.VE). The data model and its limits live in timeline.js. */
(function () {
  var V = window.VE;
  if (!V) return;
  var S = V.S, TL = V.TL, $ = V.$, el = V.el, clamp = V.clamp;

  function tab(name) { var b = document.querySelector('#tabs button[data-tab="' + name + '"]'); if (b) b.click(); }
  function clearSel(except) { if (except !== "clip") S.sel = -1; if (except !== "text") S.selText = -1; if (except !== "audio") S.selAudio = -1; }
  function curText() { return S.selText >= 0 ? S.texts[S.selText] : null; }
  function curAudio() { return S.selAudio >= 0 ? S.audios[S.selAudio] : null; }
  function replaceText(i, changes) { S.texts = S.texts.map(function (t, k) { return k === i ? TL.cleanText(TL.patch(t, changes)) : t; }); S.dirty = true; }
  function replaceAudio(i, changes) { S.audios = S.audios.map(function (a, k) { return k === i ? TL.cleanAudio(TL.patch(a, changes)) : a; }); S.dirty = true; }

  // ---------------------------------------------------------------- text: panel
  function addText() {
    V.commit(function () { var t = TL.newText(S.t, 3); S.texts = S.texts.concat([t]); clearSel("text"); S.selText = S.texts.length - 1; });
    tab("text"); setTimeout(function () { $("tx-text").focus(); $("tx-text").select(); }, 30);
  }
  $("btn-text-add").addEventListener("click", addText);
  function liveText(changes) {                      // one history entry per gesture (typing, dragging a slider)
    var i = S.selText; if (i < 0) return;
    V.gestureBegin(); replaceText(i, changes); V.drawStage(); drawLanes(); renderPanel(true);
  }
  $("tx-text").addEventListener("input", function () { liveText({ text: this.value }); });
  $("tx-size").addEventListener("input", function () { liveText({ size: +this.value / 100 }); });
  $("tx-color").addEventListener("input", function () { liveText({ color: this.value }); });
  $("tx-boxcolor").addEventListener("input", function () { liveText({ boxColor: this.value }); });
  $("tx-outline").addEventListener("change", function () { liveText({ outline: this.checked }); V.gestureEnd(); });
  $("tx-box").addEventListener("change", function () { liveText({ box: this.checked }); V.gestureEnd(); });
  $("tx-start").addEventListener("input", function () { liveText({ start: +this.value }); });
  $("tx-dur").addEventListener("input", function () { liveText({ dur: +this.value }); });
  ["tx-text", "tx-size", "tx-color", "tx-boxcolor", "tx-start", "tx-dur"].forEach(function (id) { $(id).addEventListener("change", function () { V.gestureEnd(); V.renderAll(); }); $(id).addEventListener("blur", V.gestureEnd); });
  [["tx-p-title", { x: 0.5, y: 0.45, size: 0.12 }], ["tx-p-lower", { x: 0.5, y: 0.82, size: 0.06, box: true }], ["tx-p-caption", { x: 0.5, y: 0.92, size: 0.055 }]].forEach(function (p) {
    $(p[0]).addEventListener("click", function () { if (S.selText < 0) return; V.gestureBegin(); replaceText(S.selText, p[1]); V.gestureEnd(); V.renderAll(); });
  });
  $("btn-text-dup").addEventListener("click", function () {
    var t = curText(); if (!t) return;
    V.commit(function () { var c = TL.cleanText(TL.patch(t, { id: TL.uid("t"), start: t.start + t.dur })); S.texts = S.texts.concat([c]); clearSel("text"); S.selText = S.texts.length - 1; });
  });
  $("btn-text-del").addEventListener("click", function () { deleteText(); });
  function deleteText() { if (S.selText < 0) return false; var i = S.selText; V.commit(function () { S.texts = S.texts.filter(function (_, k) { return k !== i; }); S.selText = -1; }); return true; }

  // ---------------------------------------------------------------- audio: panel
  $("btn-audio-add").addEventListener("click", function () {
    V.openDialog({ kind: "media", title: "Add audio", done: function (path) {
      V.flash("Reading " + V.baseName(path) + "…");
      V.ensureAsset(path).then(function (a) {
        if (!a.hasAudio) { V.flash(a.name + " has no sound."); return; }
        V.commit(function () { S.audios = S.audios.concat([TL.newAudio(a.id, a.dur, S.t)]); clearSel("audio"); S.selAudio = S.audios.length - 1; });
      }).catch(function (e) { V.flash("Could not add the audio: " + e.message); });
    } });
  });
  function liveAudio(changes) { var i = S.selAudio; if (i < 0) return; V.gestureBegin(); replaceAudio(i, changes); drawLanes(); V.drawCanvases(); renderPanel(true); }
  $("au-vol").addEventListener("input", function () { liveAudio({ vol: +this.value }); });
  $("au-fi").addEventListener("input", function () { liveAudio({ fi: +this.value }); });
  $("au-fo").addEventListener("input", function () { liveAudio({ fo: +this.value }); });
  $("au-start").addEventListener("input", function () { liveAudio({ start: +this.value }); });
  $("au-duck").addEventListener("change", function () { liveAudio({ duck: this.checked }); V.gestureEnd(); });
  ["au-vol", "au-fi", "au-fo", "au-start"].forEach(function (id) { $(id).addEventListener("change", function () { V.gestureEnd(); V.renderAll(); }); });
  $("btn-audio-del").addEventListener("click", function () { deleteAudio(); });
  function deleteAudio() {
    if (S.selAudio < 0) return false; var i = S.selAudio, a = S.audios[i];
    V.commit(function () { S.audios = S.audios.filter(function (_, k) { return k !== i; }); S.selAudio = -1; });
    if (pool[a.id]) { pool[a.id].pause(); delete pool[a.id]; }
    return true;
  }

  function renderPanel(light) {
    var t = curText(), a = curAudio(), active = t && S.t >= t.start && S.t < t.start + t.dur;
    $("tx-none").hidden = !!t; $("tx-edit").hidden = !t;
    if (t) {
      if (!light || document.activeElement !== $("tx-text")) $("tx-text").value = t.text;
      $("tx-size").value = Math.round(t.size * 1000) / 10; $("v-txsize").textContent = Math.round(t.size * 1000) / 10 + "%";
      $("tx-color").value = t.color; $("tx-boxcolor").value = t.boxColor; $("tx-outline").checked = t.outline; $("tx-box").checked = t.box;
      if (document.activeElement !== $("tx-start")) $("tx-start").value = t.start.toFixed(2);
      if (document.activeElement !== $("tx-dur")) $("tx-dur").value = t.dur.toFixed(2);
      $("tx-none").textContent = active ? "" : "";
    }
    $("au-none").hidden = !!a; $("au-edit").hidden = !a;
    if (a) {
      var asset = V.assetFor(a.asset);
      $("au-name").textContent = (asset ? asset.name : "?") + "  " + V.fmt(a["in"]) + " → " + V.fmt(a.out);
      $("au-vol").value = a.vol; $("v-auvol").textContent = Math.round(a.vol) + " dB";
      $("au-fi").value = a.fi; $("v-aufi").textContent = a.fi + " s"; $("au-fo").value = a.fo; $("v-aufo").textContent = a.fo + " s";
      $("au-duck").checked = a.duck; if (document.activeElement !== $("au-start")) $("au-start").value = a.start.toFixed(2);
    }
  }

  // ---------------------------------------------------------------- lanes on the timeline
  function drawLanes() {
    var tbox = $("texts"), abox = $("audios");
    Array.prototype.slice.call(tbox.querySelectorAll(".titem")).forEach(function (n) { tbox.removeChild(n); });
    Array.prototype.slice.call(abox.querySelectorAll(".aitem")).forEach(function (n) { abox.removeChild(n); });
    S.texts.forEach(function (t, i) {
      var d = el("div", "titem" + (i === S.selText ? " sel" : ""), (t.text.split("\n")[0] || "(empty)")); d.setAttribute("data-i", i);
      d.style.left = (t.start * S.zoom) + "px"; d.style.width = Math.max(10, t.dur * S.zoom - 1) + "px"; d.title = t.text;
      var hl = el("b", "h l"), hr = el("b", "h r"); hl.setAttribute("data-edge", "left"); hr.setAttribute("data-edge", "right"); d.appendChild(hl); d.appendChild(hr); tbox.appendChild(d);
    });
    S.audios.forEach(function (a, i) {
      var asset = V.assetFor(a.asset), d = el("div", "aitem" + (i === S.selAudio ? " sel" : ""), (asset ? asset.name : "?") + "  " + Math.round(a.vol) + " dB");
      d.setAttribute("data-i", i); d.style.left = (a.start * S.zoom) + "px"; d.style.width = Math.max(10, TL.audioDur(a) * S.zoom - 1) + "px";
      var hl = el("b", "h l"), hr = el("b", "h r"); hl.setAttribute("data-edge", "left"); hr.setAttribute("data-edge", "right"); d.appendChild(hl); d.appendChild(hr); abox.appendChild(d);
    });
  }

  function drawCanvases(vw, x0, dpr) {                // waveform of the audio items (called by app.js after the main waveform)
    var c = $("awave"), H = 62; c.width = vw * dpr; c.height = H * dpr; c.style.width = vw + "px"; c.style.height = H + "px"; c.style.left = x0 + "px"; c.style.right = "auto";
    var g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, vw, H);
    var col = V.cssColor("--accent", "#8b6cf0"), mid = H / 2 + 6, amp = H / 2 - 12;
    S.audios.forEach(function (a) {
      var asset = V.assetFor(a.asset), x1 = a.start * S.zoom - x0, x2 = TL.audioEnd(a) * S.zoom - x0;
      if (x2 < 0 || x1 > vw || !asset || !asset.peaks || !asset.peaks.length || !asset.dur) return;
      var per = asset.peaks.length / asset.dur; g.fillStyle = col; g.globalAlpha = 0.85;
      for (var px = Math.max(0, Math.floor(x1)); px < Math.min(vw, Math.ceil(x2)); px++) {
        var tt = a["in"] + ((x0 + px) / S.zoom - a.start), ia = Math.floor(tt * per), ib = Math.max(ia + 1, Math.ceil((tt + 1 / S.zoom) * per)), m = 0;
        for (var i = Math.max(0, ia); i < ib && i < asset.peaks.length; i++) if (asset.peaks[i] > m) m = asset.peaks[i];
        var h = Math.max(1, m * amp) * TL.audioGain(a, tt + a.start - a["in"]) / Math.pow(10, a.vol / 20);   // fades show in the picture
        g.fillRect(px, mid - h, 1, h * 2);
      }
    });
    g.globalAlpha = 1;
  }

  // mouse on the lanes: select, move (drag), trim (drag an edge)
  function laneDrag(box, kind) {
    var drag = null;
    box.addEventListener("mousedown", function (e) {
      var item = e.target.closest && e.target.closest(kind === "text" ? ".titem" : ".aitem"); if (!item || e.button !== 0) return;
      var i = +item.getAttribute("data-i"), edge = e.target.getAttribute && e.target.getAttribute("data-edge");
      clearSel(kind); if (kind === "text") S.selText = i; else S.selAudio = i;
      drag = { i: i, edge: edge, x0: e.clientX, base: V.snap(), item: kind === "text" ? S.texts[i] : S.audios[i], moved: false };
      renderPanel(); drawLanes(); V.drawStage();
      if (kind === "text") tab("text"); else tab("sound");
      e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return; var dx = (e.clientX - drag.x0) / S.zoom; if (Math.abs(dx) < 0.004 && !drag.moved) return; drag.moved = true;
      var it = drag.item, next;
      if (kind === "text") next = drag.edge ? TL.trimText(it, drag.edge, dx) : TL.patch(it, { start: Math.max(0, it.start + dx) });
      else { var asset = V.assetFor(it.asset); next = drag.edge ? TL.trimAudio(it, drag.edge, dx, asset && asset.dur) : TL.patch(it, { start: Math.max(0, it.start + dx) }); }
      if (kind === "text") S.texts = S.texts.map(function (t, k) { return k === drag.i ? TL.cleanText(next) : t; });
      else S.audios = S.audios.map(function (a, k) { return k === drag.i ? TL.cleanAudio(next) : a; });
      S.dirty = true; drawLanes(); V.drawCanvases(); V.drawStage(); renderPanel(true);
    });
    window.addEventListener("mouseup", function () { if (!drag) return; var d = drag; drag = null; if (d.moved) { S.hist.push(d.base); V.renderAll(); } });
  }
  laneDrag($("texts"), "text"); laneDrag($("audios"), "audio");
  $("texts").addEventListener("dblclick", function () { tab("text"); setTimeout(function () { $("tx-text").focus(); }, 30); });

  // ---------------------------------------------------------------- text: preview on the stage
  var tbounds = null;
  function drawStageText(g, k, W, H) {
    tbounds = null;
    TL.activeText(S.texts, S.t).forEach(function (t) {
      var size = Math.max(8, Math.round(t.size * H)) * k, lines = t.text.split("\n"), lh = size * 1.2;
      g.font = "600 " + size + "px system-ui, -apple-system, 'Segoe UI', sans-serif"; g.textBaseline = "top"; g.textAlign = "left";
      var maxw = 0; lines.forEach(function (l) { maxw = Math.max(maxw, g.measureText(l).width); });
      var h = lines.length * lh, x0 = t.x * W * k - maxw / 2, y0 = t.y * H * k - h / 2, pad = Math.max(6, size / 4);
      if (t.box) { g.globalAlpha = t.boxOpacity; g.fillStyle = t.boxColor; g.fillRect(x0 - pad, y0 - pad, maxw + pad * 2, h + pad * 2); g.globalAlpha = 1; }
      lines.forEach(function (l, n) {
        if (t.outline) { g.lineWidth = Math.max(1, size * 0.12); g.lineJoin = "round"; g.strokeStyle = "#000"; g.strokeText(l, x0, y0 + n * lh); }
        g.fillStyle = t.color; g.fillText(l, x0, y0 + n * lh);
      });
      if (S.texts[S.selText] && S.texts[S.selText].id === t.id) tbounds = { x: x0 - pad, y: y0 - pad, w: maxw + pad * 2, h: h + pad * 2, k: k };
    });
    var gz = $("tgizmo");
    if (!tbounds || V.playing()) { gz.hidden = true; return; }
    var kc = $("stage").clientWidth / g.canvas.width;
    gz.hidden = false; gz.style.left = (tbounds.x * kc) + "px"; gz.style.top = (tbounds.y * kc) + "px"; gz.style.width = (tbounds.w * kc) + "px"; gz.style.height = (tbounds.h * kc) + "px";
  }
  (function () {            // drag the selected text on the preview, mouse wheel = size
    var drag = null;
    $("tgizmo").addEventListener("mousedown", function (e) {
      var t = curText(); if (!t || e.button !== 0) return; var r = $("stage").getBoundingClientRect();
      drag = { x0: e.clientX, y0: e.clientY, tx: t.x, ty: t.y, w: r.width, h: r.height, moved: false }; V.gestureBegin(); e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return; drag.moved = true;
      var nx = drag.tx + (e.clientX - drag.x0) / drag.w, ny = drag.ty + (e.clientY - drag.y0) / drag.h;
      if (Math.abs(nx - 0.5) < 0.012) nx = 0.5;
      replaceText(S.selText, { x: nx, y: ny }); V.drawStage();
    });
    window.addEventListener("mouseup", function () { if (!drag) return; drag = null; V.gestureEnd(); V.renderAll(); });
    $("stage").addEventListener("wheel", function (e) {
      var t = curText(); if (!t || !tbounds) return;
      var r = $("stage").getBoundingClientRect(), mx = (e.clientX - r.left) / r.width, my = (e.clientY - r.top) / r.height, bx = $("tgizmo").getBoundingClientRect();
      if (e.clientX < bx.left || e.clientX > bx.right || e.clientY < bx.top || e.clientY > bx.bottom) return;       // only over the text
      e.preventDefault(); e.stopImmediatePropagation(); V.gestureBegin(); replaceText(S.selText, { size: t.size * Math.exp(-e.deltaY * 0.0015) }); V.gestureEnd(); V.renderAll();
    }, { passive: false, capture: true });
  })();

  // ---------------------------------------------------------------- audio: preview playback (one <audio> per active item)
  var pool = {};
  function stop() { Object.keys(pool).forEach(function (id) { try { pool[id].pause(); } catch (e) { /* ignore */ } }); }
  function tick() {
    var t = S.t;
    S.audios.forEach(function (a) {
      var asset = V.assetFor(a.asset), active = t >= a.start && t < TL.audioEnd(a), node = pool[a.id];
      if (!active || !asset || !asset.src) { if (node && !node.paused) node.pause(); return; }
      if (!node) { node = pool[a.id] = new Audio(); node.preload = "auto"; node.src = asset.src; }
      node.volume = clamp(TL.audioGain(a, t), 0, 1);
      var want = a["in"] + (t - a.start);
      if (node.paused) { try { node.currentTime = want; } catch (e) { /* not ready */ } var pr = node.play(); if (pr && pr.catch) pr.catch(function () { /* blocked until the next click */ }); }
      else if (Math.abs(node.currentTime - want) > 0.35) node.currentTime = want;
    });
  }

  function deleteSelected() { return deleteAudio() || deleteText(); }
  function render() { renderPanel(); drawLanes(); }
  V.layers = { drawStage: drawStageText, drawCanvases: drawCanvases, drawLanes: drawLanes, render: render, tick: tick, stop: stop, deleteSelected: deleteSelected };
  V.renderAll();
})();
