"use strict";
/* Pure timeline logic (no DOM). A sequence is an ordered list of clips {id, asset, in, out} played back to back.
   All functions return new arrays; clips are never mutated. Times are seconds. Used by app.js and tested in Node. */
(function (root) {
  var MIN_CLIP = 0.1;      // shortest clip the user can trim to
  var MIN_PIECE = 0.05;    // pieces shorter than this are dropped when cutting
  var counter = 0;

  function uid(prefix) { counter += 1; return (prefix || "c") + Date.now().toString(36) + counter.toString(36); }
  function round(t) { return Math.round(t * 1000) / 1000; }
  function copy(c, extra) {
    var o = { id: c.id, asset: c.asset, "in": c["in"], out: c.out };
    if (c.tf) o.tf = { s: c.tf.s, x: c.tf.x, y: c.tf.y };          // position/scale travel with the pieces of a split
    for (var k in extra) o[k] = extra[k];
    return o;
  }
  function dur(c) { return c.out - c["in"]; }

  function layout(clips) {
    var t = 0, items = clips.map(function (c) { var it = { clip: c, start: t, end: t + dur(c), dur: dur(c) }; t += dur(c); return it; });
    return { items: items, total: t };
  }
  function total(clips) { return layout(clips).total; }

  // which clip plays at sequence time t; src = time inside the source file
  function at(clips, t) {
    var L = layout(clips);
    if (!L.items.length) return null;
    var x = Math.max(0, Math.min(t, L.total));
    for (var i = 0; i < L.items.length; i++) {
      var it = L.items[i];
      if (x < it.end || i === L.items.length - 1) return { index: i, clip: it.clip, start: it.start, end: it.end, src: it.clip["in"] + Math.min(x - it.start, it.dur) };
    }
    return null;
  }

  function split(clips, t, newId) {
    var hit = at(clips, t);
    if (!hit) return { clips: clips, index: -1, changed: false };
    var local = t - hit.start;
    if (local < MIN_PIECE || hit.end - t < MIN_PIECE) return { clips: clips, index: hit.index, changed: false };
    var c = hit.clip, cut = round(c["in"] + local), out = clips.slice();
    out.splice(hit.index, 1, copy(c, { out: cut }), copy(c, { id: newId || uid(), "in": cut }));
    return { clips: out, index: hit.index + 1, changed: true };
  }

  function removeIndex(clips, i) { return clips.filter(function (_, k) { return k !== i; }); }

  // ripple-delete the sequence range [a, b]
  function deleteRange(clips, a, b, idGen) {
    if (b < a) { var s = a; a = b; b = s; }
    var out = [];
    layout(clips).items.forEach(function (it) {
      if (it.end <= a || it.start >= b) { out.push(it.clip); return; }
      var c = it.clip;
      if (a - it.start >= MIN_PIECE) out.push(copy(c, { out: round(c["in"] + (a - it.start)) }));
      if (it.end - b >= MIN_PIECE) out.push(copy(c, { id: (a - it.start >= MIN_PIECE) ? (idGen || uid)() : c.id, "in": round(c["in"] + (b - it.start)) }));
    });
    return out;
  }

  // remove source-time ranges [[s,e],...] from one clip; returns the remaining pieces in order
  function subtractRanges(clip, ranges, idGen) {
    var cuts = ranges.map(function (r) { return [Math.max(r[0], clip["in"]), Math.min(r[1], clip.out)]; })
      .filter(function (r) { return r[1] - r[0] > 0; }).sort(function (x, y) { return x[0] - y[0] });
    if (!cuts.length) return [clip];
    var pieces = [], pos = clip["in"];
    cuts.forEach(function (r) {
      if (r[0] - pos >= MIN_PIECE) pieces.push([pos, r[0]]);
      pos = Math.max(pos, r[1]);
    });
    if (clip.out - pos >= MIN_PIECE) pieces.push([pos, clip.out]);
    return pieces.map(function (p, k) { return copy(clip, { id: k === 0 ? clip.id : (idGen || uid)(), "in": round(p[0]), out: round(p[1]) }); });
  }

  // cut silences (source-time ranges of one asset) out of the clips that use that asset (optionally only one clip)
  function applySilence(clips, assetId, ranges, onlyClipId, idGen) {
    var out = [];
    clips.forEach(function (c) {
      if (c.asset === assetId && (!onlyClipId || c.id === onlyClipId)) subtractRanges(c, ranges, idGen).forEach(function (p) { out.push(p); });
      else out.push(c);
    });
    return out;
  }

  // drag an edge of clip i by delta seconds (ripple: later clips shift automatically). assetDur limits the right edge.
  function trim(clips, i, edge, delta, assetDur) {
    var c = clips[i]; if (!c) return clips;
    var lo = c["in"], hi = c.out;
    if (edge === "left") lo = Math.max(0, Math.min(c["in"] + delta, c.out - MIN_CLIP));
    else hi = Math.min(assetDur == null ? Infinity : assetDur, Math.max(c.out + delta, c["in"] + MIN_CLIP));
    var out = clips.slice(); out[i] = copy(c, { "in": round(lo), out: round(hi) });
    return out;
  }

  // move clip `from` so it ends up at index `to` (index in the resulting list)
  function move(clips, from, to) {
    if (from === to || from < 0 || from >= clips.length) return clips;
    var out = clips.slice(), item = out.splice(from, 1)[0];
    out.splice(Math.max(0, Math.min(to, out.length)), 0, item);
    return out;
  }

  // where would a clip dragged to sequence time t be inserted? (index among the OTHER clips)
  function dropIndex(clips, from, t) {
    var idx = 0, L = layout(clips.filter(function (_, k) { return k !== from; }));
    L.items.forEach(function (it) { if (t > it.start + it.dur / 2) idx++; });
    return idx;
  }

  function insertAt(clips, index, clip) { var out = clips.slice(); out.splice(Math.max(0, Math.min(index, out.length)), 0, clip); return out; }

  // payload for the server: clips with real file paths
  function forExport(clips, assets) {
    return clips.map(function (c) { var o = { path: assets[c.asset].path, "in": c["in"], out: c.out }; if (c.tf) o.tf = cleanTf(c.tf); return o; });
  }

  // ---- canvas + per-clip transform (mirrored exactly in editor/project.py)
  // tf = {s: scale relative to "fit inside the canvas", x, y: centre offset as a fraction of canvas width/height}
  var ASPECTS = { "16:9": [16, 9], "9:16": [9, 16], "1:1": [1, 1], "4:5": [4, 5] };
  var SHORTS = [360, 480, 720, 1080, 1440, 2160];
  function even(n) { return Math.max(2, Math.round(n / 2) * 2); }
  function canvasSize(aspect, short, firstW, firstH) {
    if (!ASPECTS[aspect]) return [even(firstW || 1280), even(firstH || 720)];      // "auto": the first clip decides
    var a = ASPECTS[aspect], sh = SHORTS.indexOf(short) >= 0 ? short : 1080;
    return a[0] >= a[1] ? [even(sh * a[0] / a[1]), even(sh)] : [even(sh), even(sh * a[1] / a[0])];
  }
  function cleanTf(tf) {
    var t = tf || {}, num = function (v, d, lo, hi) { v = Number(v); return isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d; };
    return { s: num(t.s, 1, 0.05, 10), x: num(t.x, 0, -3, 3), y: num(t.y, 0, -3, 3) };
  }
  function fgRect(iw, ih, W, H, tf) {          // where the picture sits on the canvas: [x, y, w, h] in canvas pixels
    var t = cleanTf(tf), f = Math.min(W / iw, H / ih), w = even(iw * f * t.s), h = even(ih * f * t.s);
    return [Math.round(W / 2 + t.x * W - w / 2), Math.round(H / 2 + t.y * H - h / 2), w, h];
  }
  function fillScale(iw, ih, W, H) { return Math.max(W / iw, H / ih) / Math.min(W / iw, H / ih); }   // scale at which the picture covers the canvas
  function isDefaultTf(tf) { var t = cleanTf(tf); return t.s === 1 && t.x === 0 && t.y === 0; }

  // ---- text layer and audio track: items on their own lanes, positioned in absolute timeline seconds
  var HEXC = /^#[0-9a-fA-F]{6}$/;
  function clampN(v, d, lo, hi) { v = Number(v); return isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d; }
  function newText(start, dur, id) {
    return { id: id || uid("t"), text: "Your text", start: round(Math.max(0, start || 0)), dur: dur || 3, x: 0.5, y: 0.82, size: 0.07,
      color: "#ffffff", box: false, boxColor: "#000000", boxOpacity: 0.55, outline: true };
  }
  function cleanText(t) {          // same limits as sanitize_texts() in editor/project.py
    t = t || {};
    return { id: String(t.id || uid("t")).slice(0, 40), text: String(t.text == null ? "" : t.text).slice(0, 500),
      start: round(clampN(t.start, 0, 0, 86400)), dur: round(clampN(t.dur, 3, 0.1, 3600)),
      x: clampN(t.x, 0.5, -0.5, 1.5), y: clampN(t.y, 0.82, -0.5, 1.5), size: clampN(t.size, 0.07, 0.01, 0.5),
      color: HEXC.test(t.color || "") ? t.color : "#ffffff", box: !!t.box, boxColor: HEXC.test(t.boxColor || "") ? t.boxColor : "#000000",
      boxOpacity: clampN(t.boxOpacity, 0.55, 0, 1), outline: t.outline !== false };
  }
  function patch(item, changes) { var o = {}, k; for (k in item) o[k] = item[k]; for (k in changes) o[k] = changes[k]; return o; }
  function trimText(t, edge, delta) {
    if (edge === "left") { var ns = clampN(t.start + delta, t.start, 0, t.start + t.dur - 0.2); return patch(t, { start: round(ns), dur: round(t.dur - (ns - t.start)) }); }
    return patch(t, { dur: round(Math.max(0.2, t.dur + delta)) });
  }
  function newAudio(assetId, assetDur, start, id) {
    return { id: id || uid("m"), asset: assetId, "in": 0, out: round(assetDur), start: round(Math.max(0, start || 0)), vol: -10, fi: 0, fo: 1, duck: true };
  }
  function audioDur(a) { return a.out - a["in"]; }
  function audioEnd(a) { return a.start + audioDur(a); }
  function cleanAudio(a) {
    a = a || {};
    return { id: String(a.id || uid("m")).slice(0, 40), asset: String(a.asset), "in": round(Math.max(0, Number(a["in"]) || 0)), out: round(Math.max(0, Number(a.out) || 0)),
      start: round(clampN(a.start, 0, 0, 86400)), vol: clampN(a.vol, -10, -60, 24), fi: clampN(a.fi, 0, 0, 60), fo: clampN(a.fo, 0, 0, 60), duck: !!a.duck };
  }
  function trimAudio(a, edge, delta, assetDur) {            // the picture of the sound stays where it is: trimming the left edge moves the start with it
    if (edge === "left") { var ni = clampN(a["in"] + delta, a["in"], 0, a.out - 0.2); return patch(a, { "in": round(ni), start: round(a.start + (ni - a["in"])) }); }
    return patch(a, { out: round(clampN(a.out + delta, a.out, a["in"] + 0.2, assetDur == null ? Infinity : assetDur)) });
  }
  function audioGain(a, t) {                                // linear gain of an audio item at timeline time t (volume + fades), for the preview
    var g = Math.pow(10, a.vol / 20), into = t - a.start, left = audioEnd(a) - t;
    if (a.fi > 0 && into < a.fi) g *= Math.max(0, into / a.fi);
    if (a.fo > 0 && left < a.fo) g *= Math.max(0, left / a.fo);
    return g;
  }
  function activeText(texts, t) { return texts.filter(function (x) { return t >= x.start && t < x.start + x.dur; }); }
  function activeAudio(audios, t) { return audios.filter(function (a) { return t >= a.start && t < audioEnd(a); }); }

  function createHistory(limit) {
    var past = [], future = [], max = limit || 100;
    return {
      push: function (state) { past.push(JSON.stringify(state)); if (past.length > max) past.shift(); future = []; },
      undo: function (current) { if (!past.length) return null; future.push(JSON.stringify(current)); return JSON.parse(past.pop()); },
      redo: function (current) { if (!future.length) return null; past.push(JSON.stringify(current)); return JSON.parse(future.pop()); },
      canUndo: function () { return past.length > 0; }, canRedo: function () { return future.length > 0; },
    };
  }

  var api = { MIN_CLIP: MIN_CLIP, MIN_PIECE: MIN_PIECE, uid: uid, layout: layout, total: total, at: at, split: split, removeIndex: removeIndex,
    deleteRange: deleteRange, subtractRanges: subtractRanges, applySilence: applySilence, trim: trim, move: move, dropIndex: dropIndex,
    insertAt: insertAt, forExport: forExport, createHistory: createHistory, round: round,
    newText: newText, cleanText: cleanText, trimText: trimText, newAudio: newAudio, cleanAudio: cleanAudio, trimAudio: trimAudio,
    audioDur: audioDur, audioEnd: audioEnd, audioGain: audioGain, activeText: activeText, activeAudio: activeAudio, patch: patch,
    ASPECTS: ASPECTS, SHORTS: SHORTS, canvasSize: canvasSize, cleanTf: cleanTf, fgRect: fgRect, fillScale: fillScale, isDefaultTf: isDefaultTf };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VETimeline = api;
})(typeof window !== "undefined" ? window : this);
