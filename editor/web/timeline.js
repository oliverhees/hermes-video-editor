"use strict";
/* Pure timeline logic (no DOM). A sequence is an ordered list of clips {id, asset, in, out} played back to back.
   All functions return new arrays; clips are never mutated. Times are seconds. Used by app.js and tested in Node. */
(function (root) {
  var MIN_CLIP = 0.1;      // shortest clip the user can trim to
  var MIN_PIECE = 0.05;    // pieces shorter than this are dropped when cutting
  var counter = 0;

  function uid(prefix) { counter += 1; return (prefix || "c") + Date.now().toString(36) + counter.toString(36); }
  function round(t) { return Math.round(t * 1000) / 1000; }
  function copy(c, extra) { var o = { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; for (var k in extra) o[k] = extra[k]; return o; }
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
    return clips.map(function (c) { return { path: assets[c.asset].path, "in": c["in"], out: c.out }; });
  }

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
    insertAt: insertAt, forExport: forExport, createHistory: createHistory, round: round };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VETimeline = api;
})(typeof window !== "undefined" ? window : this);
