"use strict";
/* The Clip tab: speed, still frame, transition into the clip and the clip's look and sound (brightness, contrast, saturation,
   volume, mute, fades). Everything applies to the selected clip, or to the clip under the playhead. */
(function () {
  var V = window.VE;
  if (!V || !V.layers) return;
  var S = V.S, TL = V.TL, $ = V.$, L = V.layers;
  var SPEEDS = [0.25, 0.5, 1, 1.5, 2, 3, 4];

  function cur() { var i = V.targetIndex(); return i >= 0 ? { i: i, c: S.clips[i] } : null; }
  function live(changes) {                         // one history entry per gesture (dragging a slider)
    var t = cur(); if (!t) return;
    V.gestureBegin();
    V.patchClips(function (cl) { return cl.map(function (c, k) { return k === t.i ? TL.copy(c, changes) : c; }); });
  }
  function liveAdj(changes) {
    var t = cur(); if (!t) return;
    var adj = TL.cleanAdj(Object.assign({}, t.c.adj || {}, changes));
    live({ adj: TL.isDefaultAdj(adj) ? null : adj });
  }
  function done() { V.gestureEnd(); V.invalidatePreload(); V.syncPlayback(); V.renderAll(); }

  // ---- speed
  SPEEDS.forEach(function (v) {
    var b = V.el("button", "btn small", v + "×"); b.setAttribute("data-speed", v);
    b.addEventListener("click", function () { live({ sp: v === 1 ? null : v }); done(); });
    $("fx-speeds").appendChild(b);
  });
  $("fx-speed").addEventListener("input", function () { var v = +this.value; live({ sp: Math.abs(v - 1) < 0.01 ? null : v }); });
  $("fx-speed").addEventListener("change", done);

  // ---- still frame: a picture of the frame under the playhead, held for a while
  $("btn-fx-freeze").addEventListener("click", function () {
    var hit = TL.at(S.clips, S.t), len = Math.max(0.1, Math.min(30, +$("fx-freeze-len").value || 2));
    if (!hit || hit.clip.freeze) { V.flash("Put the playhead on a clip first."); return; }
    var a = V.assetFor(hit.clip.asset); if (!a || !a.hasVideo) { V.flash("This clip has no picture."); return; }
    var src = Math.min(hit.src, Math.max(0, (a.dur || hit.src) - 0.1)), local = S.t - hit.start, ix;
    V.ops.edit(function (cl) {
      var r = TL.split(cl, S.t, TL.uid("c"));
      ix = r.changed ? r.index : (local < TL.MIN_PIECE ? hit.index : hit.index + 1);
      var adj = hit.clip.adj ? Object.assign({}, hit.clip.adj, { fi: 0, fo: 0 }) : null;
      var still = TL.copy(hit.clip, { id: TL.uid("c"), "in": TL.round(src), out: TL.round(src + 0.1), freeze: len, sp: null, tr: null, adj: adj && !TL.isDefaultAdj(adj) ? adj : null });
      S.sel = ix; return TL.insertAt(r.changed ? r.clips : cl, ix, still);
    });
  });

  // ---- transition into the selected clip
  TL.TRANSITIONS.forEach(function (n) { var o = V.el("option", "", n); o.value = n; $("fx-tr").appendChild(o); });
  function setTr() {
    var t = cur(); if (!t) return;
    var type = $("fx-tr").value;
    V.ops.edit(function (cl) { return cl.map(function (c, k) { return k === t.i ? TL.copy(c, { tr: type ? { type: type, dur: +$("fx-trlen").value || 0.5 } : null }) : c; }); });
  }
  $("fx-tr").addEventListener("change", setTr);
  $("fx-trlen").addEventListener("input", function () {
    var t = cur(); if (!t || !t.c.tr) return;
    live({ tr: { type: t.c.tr.type, dur: +this.value } });
  });
  $("fx-trlen").addEventListener("change", done);

  // ---- look and sound
  [["fx-br", function (v) { return { br: v / 100 }; }], ["fx-ct", function (v) { return { ct: v / 100 }; }], ["fx-sa", function (v) { return { sa: v / 100 }; }],
   ["fx-vol", function (v) { return { vol: v }; }], ["fx-fi", function (v) { return { fi: v }; }], ["fx-fo", function (v) { return { fo: v }; }]].forEach(function (p) {
    $(p[0]).addEventListener("input", function () { liveAdj(p[1](+this.value)); });
    $(p[0]).addEventListener("change", done);
  });
  $("fx-mute").addEventListener("change", function () { liveAdj({ mute: this.checked }); done(); });
  $("btn-fx-reset").addEventListener("click", function () { live({ adj: null }); done(); });
  $("btn-fx-all").addEventListener("click", function () {
    var t = cur(); if (!t) return;
    var adj = t.c.adj ? TL.cleanAdj(Object.assign({}, t.c.adj, { fi: 0, fo: 0 })) : null;
    V.ops.edit(function (cl) { return cl.map(function (c) { return TL.copy(c, { adj: adj && !TL.isDefaultAdj(adj) ? adj : null }); }); });
  });

  function render() {
    var t = cur(), c = t && t.c, adj = TL.cleanAdj(c && c.adj), on = !!c;
    var info = !c ? "Add a clip first." : (S.sel < 0 ? "Applies to the clip under the playhead. " : "Applies to the selected clip. ") + (c.freeze ? "This clip is a still frame." : "");
    $("fx-hint").textContent = info;
    ["fx-speed", "fx-freeze-len", "btn-fx-freeze", "fx-br", "fx-ct", "fx-sa", "fx-vol", "fx-mute", "fx-fi", "fx-fo", "btn-fx-reset", "btn-fx-all"].forEach(function (id) { $(id).disabled = !on; });
    $("fx-speed").disabled = !on || !!(c && c.freeze);
    $("fx-tr").disabled = !on || t.i === 0; $("fx-trlen").disabled = !on || t.i === 0 || !(c && c.tr);
    var sp = (c && c.sp) || 1;
    if (document.activeElement !== $("fx-speed")) $("fx-speed").value = sp;
    $("v-fxspeed").textContent = (Math.round(sp * 100) / 100) + "×";
    document.querySelectorAll("#fx-speeds button").forEach(function (b) { b.classList.toggle("on", Math.abs(+b.getAttribute("data-speed") - sp) < 0.001); });
    $("fx-tr").value = c && c.tr ? c.tr.type : ""; if (document.activeElement !== $("fx-trlen")) $("fx-trlen").value = c && c.tr ? c.tr.dur : 0.5;
    $("v-fxtrlen").textContent = ((c && c.tr) ? c.tr.dur : 0.5) + " s";
    $("fx-tr-note").textContent = t && t.i === 0 ? "The first clip has nothing before it to blend with." : "The picture blends from the clip before into this one. It is capped at half the length of the shorter clip. The preview shows a hard cut; the export blends.";
    [["fx-br", Math.round(adj.br * 100), "v-fxbr", "%"], ["fx-ct", Math.round(adj.ct * 100), "v-fxct", "%"], ["fx-sa", Math.round(adj.sa * 100), "v-fxsa", "%"],
     ["fx-vol", Math.round(adj.vol), "v-fxvol", " dB"], ["fx-fi", adj.fi, "v-fxfi", " s"], ["fx-fo", adj.fo, "v-fxfo", " s"]].forEach(function (p) {
      if (document.activeElement !== $(p[0])) $(p[0]).value = p[1]; $(p[2]).textContent = p[1] + p[3];
    });
    $("fx-mute").checked = adj.mute;
  }
  var o = { render: L.render };
  L.render = function () { o.render(); render(); };
  V.renderAll();
})();
