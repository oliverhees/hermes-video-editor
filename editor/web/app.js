"use strict";
/* Video Editor UI: plain JS, no dependencies. Talks to the local server it was loaded from.
   The edit model (clips, split, ripple delete, trim, reorder, undo) lives in timeline.js and is unit-tested separately. */
(function () {
  var TL = window.VETimeline;
  var Q = new URLSearchParams(location.search);
  var TOKEN = Q.get("t") || "";
  var $ = function (id) { return document.getElementById(id); };
  // assets: files that were added (id -> {path,name,info,dur,src,peaks,thumbs,...}); clips: the sequence, played back to back
  var S = {
    assets: {}, clips: [], sel: -1, t: 0, zoom: 80, mark: { a: null, b: null }, hist: TL.createHistory(100),
    projectPath: null, projectName: "", dirty: false, config: null, anchor: "center", dlgPath: "", fitted: false,
  };

  // ---------------------------------------------------------------- api
  function url(route, params) {
    var p = new URLSearchParams(params || {});
    p.set("t", TOKEN);
    return route + "?" + p.toString();
  }
  function api(route, params, body) {
    var opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    return fetch(url(route, params), opt).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok || j.ok === false) { var e = new Error(j.error || ("HTTP " + r.status)); e.hint = j.hint; throw e; }
        return j;
      });
    });
  }
  function store(key, val) { try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; } }

  // ---------------------------------------------------------------- helpers
  function fmt(t, tenths) {
    if (!isFinite(t)) t = 0;
    var m = Math.floor(t / 60), s = t - m * 60;
    return m + ":" + (s < 10 ? "0" : "") + s.toFixed(tenths === false ? 0 : 1);
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function busy(msg) { var o = $("overlay"); o.hidden = !msg; o.textContent = msg || ""; $("empty").hidden = S.clips.length > 0; }

  // ---------------------------------------------------------------- theme (sent by the Hermes Desktop page)
  var HEX = /^#[0-9a-f]{6}$/i;
  function applyTheme(t) {
    if (!t) return;
    var root = document.documentElement;
    if (t.theme === "light" || t.theme === "dark") root.setAttribute("data-theme", t.theme);
    if (HEX.test(t.bg || "") && HEX.test(t.fg || "")) { root.style.setProperty("--bg", t.bg); root.style.setProperty("--text", t.fg); root.setAttribute("data-derive", "1"); }
    if (HEX.test(t.accent || "")) root.style.setProperty("--accent", t.accent);
    if (S.clips.length) drawAll();
  }
  applyTheme({ theme: Q.get("theme"), bg: Q.get("bg"), fg: Q.get("fg"), accent: Q.get("accent") });
  window.addEventListener("message", function (e) {          // live theme changes, only from the page that embeds us
    if (window.parent === window || e.source !== window.parent || !e.data || e.data.type !== "ve-theme") return;
    applyTheme(e.data);
  });
  function cssColor(name, fallback) {                          // resolve a CSS variable to rgb() for canvas drawing
    var probe = document.createElement("span"); probe.style.color = "var(" + name + ")"; document.body.appendChild(probe);
    var c = getComputedStyle(probe).color; document.body.removeChild(probe); return c || fallback;
  }

  // ---------------------------------------------------------------- tabs / controls
  document.querySelectorAll("#tabs button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll("#tabs button").forEach(function (x) { x.classList.toggle("on", x === b); });
      document.querySelectorAll(".pane").forEach(function (p) { p.classList.toggle("on", p.getAttribute("data-pane") === b.getAttribute("data-tab")); });
    });
  });
  $("in-noise").addEventListener("input", function () { $("v-noise").textContent = this.value + " dB"; });
  $("in-minsil").addEventListener("input", function () { $("v-minsil").textContent = this.value + " s"; });
  $("in-lufs").addEventListener("input", function () { $("v-lufs").textContent = this.value + " LUFS"; });
  $("in-reframe").addEventListener("change", updateGuide);
  $("in-anchor").addEventListener("change", function () { S.anchor = this.value; updateGuide(); });
  $("in-speed").addEventListener("change", renderInfo);

  // ---------------------------------------------------------------- file dialog (add clips / open + save projects / pick files for tools)
  var PICK = null;   // {kind, folder, save, title, done} while the dialog is used for something other than adding a clip
  function openDialog(pick) {
    PICK = pick && pick.kind ? pick : null;
    $("modal").hidden = false;
    $("dlg-usefolder").hidden = !(PICK && (PICK.folder || PICK.save));
    $("dlg-usefolder").textContent = PICK && PICK.save ? "Save here" : "Use this folder";
    $("dlg-name").hidden = !(PICK && PICK.save); if (PICK && PICK.save) $("dlg-name").value = S.projectName || "my-project";
    $("dlg-title").textContent = PICK && PICK.title ? PICK.title : "Add a video";
    browse(S.dlgPath || store("ve.dir") || "");
    var show = !PICK; $("dlg-recent").hidden = !show; if (!show) $("dlg-recent-title").hidden = true;
    if (show) fillRecent($("dlg-recent"), $("dlg-recent-title"), closeDialog);
  }
  function fillRecent(list, title, after) {
    api("/api/recent").then(function (r) {
      list.textContent = ""; title.hidden = !r.files.length;
      r.files.slice(0, 6).forEach(function (f) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", "🎬 " + f.name)); it.title = f.path;
        it.addEventListener("click", function () { if (after) after(); addClipFromPath(f.path); }); list.appendChild(it);
      });
    }).catch(function () { title.hidden = true; });
  }
  function closeDialog() { $("modal").hidden = true; }
  function browse(path) {
    $("dlg-err").textContent = "";
    var q = path ? { path: path } : {}; if (PICK && PICK.kind) q.kind = PICK.kind;
    api("/api/ls", q).then(function (d) {
      S.dlgPath = d.path; store("ve.dir", d.path);
      $("dlg-path").value = d.path;
      var list = $("dlg-list"); list.textContent = "";
      if (d.parent) { var up = el("div", "item", ".. (up)"); up.addEventListener("click", function () { browse(d.parent); }); list.appendChild(up); }
      d.dirs.forEach(function (x) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", "📁 " + x.name));
        it.addEventListener("click", function () { browse(d.path + sep(d.path) + x.name); }); list.appendChild(it);
      });
      d.files.forEach(function (x) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", (PICK && PICK.kind === "project" ? "📄 " : "🎬 ") + x.name));
        it.appendChild(el("span", "muted", (x.size / 1048576).toFixed(1) + " MB"));
        it.addEventListener("click", function () {
          var full = d.path + sep(d.path) + x.name; closeDialog();
          if (PICK) { if (PICK.done) PICK.done(full); } else addClipFromPath(full);
        }); list.appendChild(it);
      });
      if (!d.dirs.length && !d.files.length) list.appendChild(el("div", "muted", "No folders or files here."));
    }).catch(function (e) { $("dlg-err").textContent = e.message + (e.hint ? " - " + e.hint : ""); });
  }
  function sep(p) { return p.indexOf("\\") >= 0 && p.indexOf("/") < 0 ? "\\" : "/"; }
  function openProjectDialog() { openDialog({ kind: "project", title: "Open a project", done: loadProjectFile }); }
  $("btn-open").addEventListener("click", function () { openDialog(); });
  $("btn-open2").addEventListener("click", function () { openDialog(); });
  $("btn-openproj").addEventListener("click", openProjectDialog);
  $("btn-openproj2").addEventListener("click", openProjectDialog);
  $("dlg-close").addEventListener("click", closeDialog);
  $("dlg-usefolder").addEventListener("click", function () {
    var cb = PICK && PICK.done, dir = S.dlgPath, save = PICK && PICK.save, name = $("dlg-name").value.trim();
    if (save && !name) { $("dlg-err").textContent = "Give the project a name."; return; }
    closeDialog(); if (cb) cb(save ? dir + sep(dir) + name : dir);
  });
  $("dlg-path").addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var v = this.value.trim();
    if (/\.[A-Za-z0-9]{2,4}$/.test(v) && !(PICK && (PICK.folder || PICK.save))) { var cb = PICK && PICK.done; closeDialog(); if (PICK) { if (cb) cb(v); } else addClipFromPath(v); } else browse(v);
  });

  // ---------------------------------------------------------------- assets (the files behind the clips)
  function baseName(p) { return String(p).replace(/\\/g, "/").split("/").pop(); }
  function registerAsset(id, path, name, uploaded) {
    var a = { id: id, path: path, name: name || baseName(path), uploaded: !!uploaded, info: null, dur: 0, hasAudio: false, hasVideo: false,
      src: null, peaks: null, thumbs: null, cacheId: null, state: "probing", error: null };
    S.assets[id] = a;
    return api("/api/probe", { path: path }).then(function (info) {
      a.info = info; a.dur = info.duration_s || 0; a.hasAudio = !!info.has_audio; a.hasVideo = !!info.has_video; a.state = "preparing";
      var h264 = !!document.createElement("video").canPlayType('video/mp4; codecs="avc1.42E01E"');
      return api("/api/prepare", null, { path: path, h264: h264 }).then(function (r) { pollPrepare(a, r.job); return a; });
    }).catch(function (e) { a.state = "missing"; a.error = e.message; renderAll(); throw e; });
  }
  function pollPrepare(a, jobId) {
    (function tick() {
      api("/api/job", { id: jobId }).then(function (j) {
        var r = j.result || {};
        if (r.cache_id && !a.cacheId) a.cacheId = r.cache_id;
        if (r.playback && !a.src) {
          a.src = r.playback.kind === "original" ? url("/api/media", { path: a.path }) : url("/api/cache", { id: r.cache_id, name: r.playback.name });
          if (!$("video").getAttribute("data-src")) $("video").setAttribute("data-src", a.src);
          a.state = "ready"; busy(null); syncPlayback();
        }
        if (r.thumbs && !a.thumbs) a.thumbs = r.thumbs;
        if (r.has_waveform && !a.peaks) api("/api/waveform", { id: r.cache_id }).then(function (p) { a.peaks = p; drawCanvases(); });
        if (j.state === "running") setTimeout(tick, 600);
        else if (j.state === "error" && !a.src) { a.state = "nopreview"; a.error = j.error.error; busy("Preview unavailable for " + a.name + ": " + j.error.error + " You can still cut and export."); }
        renderAll();
      }).catch(function () { setTimeout(tick, 1500); });
    })();
  }
  function assetFor(id) { return S.assets[id] || null; }
  function currentPath() {                       // the file under the selection, or under the playhead
    var c = S.sel >= 0 ? S.clips[S.sel] : (currentHit() && currentHit().clip), a = c && assetFor(c.asset);
    return a ? a.path : "";
  }
  function findAssetByPath(path) { for (var k in S.assets) if (S.assets[k].path === path) return S.assets[k]; return null; }

  // ---------------------------------------------------------------- editing (every change goes through edit() so undo/redo work)
  function snap() { return { clips: S.clips, sel: S.sel }; }
  function edit(fn) {
    S.hist.push(snap());
    var next = fn(S.clips);
    if (next) S.clips = next;
    S.dirty = true; if (S.sel >= S.clips.length) S.sel = S.clips.length - 1; afterEdit();
  }
  function afterEdit() { S.t = Math.min(S.t, TL.total(S.clips)); invalidatePreload(); syncPlayback(); renderAll(); }
  function undo() { var p = S.hist.undo(snap()); if (p) { S.clips = p.clips; S.sel = p.sel; S.dirty = true; afterEdit(); } }
  function redo() { var p = S.hist.redo(snap()); if (p) { S.clips = p.clips; S.sel = p.sel; S.dirty = true; afterEdit(); } }

  function addClipFromPath(path, uploaded) {
    busy("Reading " + baseName(path) + "…");
    var existing = findAssetByPath(path), p = existing ? Promise.resolve(existing) : registerAsset(TL.uid("a"), path, null, uploaded);
    return p.then(function (a) {
      busy(a.src ? null : "Preparing preview…");
      if (!a.dur) throw new Error("Could not read the length of " + a.name);
      var at = S.sel >= 0 ? S.sel + 1 : S.clips.length, clip = { id: TL.uid("c"), asset: a.id, "in": 0, out: TL.round(a.dur) };
      var first = S.clips.length === 0;
      edit(function (c) { S.sel = at; return TL.insertAt(c, at, clip); });
      if (first) { S.fitted = true; fit(); seek(0); }
      else if (TL.total(S.clips) * S.zoom > $("tl-scroll").clientWidth) fit();      // keep the whole timeline in view
      return a;
    }).catch(function (e) { busy("Could not add the file: " + e.message + (e.hint ? " (" + e.hint + ")" : "")); });
  }
  function loadFile(path, uploaded) { return addClipFromPath(path, uploaded); }     // used by the tools tab ("Add result to timeline")

  function doSplit() {
    var r = TL.split(S.clips, S.t, TL.uid("c"));
    if (!r.changed) { flash("Move the playhead inside a clip to split it."); return; }
    edit(function () { S.sel = r.index; return r.clips; });
  }
  function doDelete() {
    if (S.sel < 0 || S.sel >= S.clips.length) { flash("Select a clip first (click it)."); return; }
    var i = S.sel; edit(function (c) { S.sel = Math.min(i, c.length - 2); return TL.removeIndex(c, i); });
  }
  function doDuplicate() {
    if (S.sel < 0) { flash("Select a clip first."); return; }
    var c = S.clips[S.sel], i = S.sel;
    edit(function (cl) { S.sel = i + 1; return TL.insertAt(cl, i + 1, { id: TL.uid("c"), asset: c.asset, "in": c["in"], out: c.out }); });
  }
  function setIn() { S.mark.a = S.t; if (S.mark.b != null && S.mark.b <= S.mark.a) S.mark.b = null; renderAll(); }
  function setOut() { S.mark.b = S.t; if (S.mark.a != null && S.mark.a >= S.mark.b) S.mark.a = null; renderAll(); }
  function cutRange() {
    var a = S.mark.a, b = S.mark.b;
    if (a == null || b == null || b - a < 0.05) { flash("Mark a range first (I and O)."); return; }
    S.mark = { a: null, b: null }; edit(function (c) { return TL.deleteRange(c, a, b); });
  }
  function flash(msg) { $("marks").textContent = msg; setTimeout(renderMarks, 2200); }
  $("btn-split").addEventListener("click", doSplit);
  $("btn-del").addEventListener("click", doDelete);
  $("btn-dup").addEventListener("click", doDuplicate);
  $("btn-in").addEventListener("click", setIn);
  $("btn-out").addEventListener("click", setOut);
  $("btn-cut").addEventListener("click", cutRange);
  $("btn-undo").addEventListener("click", undo);
  $("btn-redo").addEventListener("click", redo);
  $("btn-silence").addEventListener("click", function () {
    if (!S.clips.length) { flash("Add a clip first."); return; }
    var btn = this, targets = S.sel >= 0 ? [S.clips[S.sel]] : S.clips, byAsset = {};
    targets.forEach(function (c) { var a = assetFor(c.asset); if (a && a.hasAudio) byAsset[c.asset] = true; });
    var ids = Object.keys(byAsset); if (!ids.length) { flash("These clips have no audio, so there is no silence to find."); return; }
    btn.disabled = true; btn.textContent = "Searching…";
    var noise = +$("in-noise").value, minS = +$("in-minsil").value, pad = 0.1, found = {};
    Promise.all(ids.map(function (id) {
      return api("/api/silence", null, { path: assetFor(id).path, noise_db: noise, min_silence_s: minS }).then(function (r) {
        found[id] = r.silences.filter(function (s) { return s.end_s - s.start_s > 2 * pad + 0.02; }).map(function (s) { return [s.start_s + pad, s.end_s - pad]; });
      });
    })).then(function () {
      var count = 0, only = S.sel >= 0 ? S.clips[S.sel].id : null, gen = function () { return TL.uid("c"); };
      edit(function (c) { ids.forEach(function (id) { count += found[id].length; c = TL.applySilence(c, id, found[id], only, gen); }); S.sel = -1; return c; });
      flash(count ? "Cut " + count + " silent parts." : "No silence found at this level.");
      btn.disabled = false; btn.textContent = "Remove silences";
    }).catch(function (e) { btn.disabled = false; btn.textContent = "Remove silences"; flash(e.message); });
  });

  // ---------------------------------------------------------------- info panel
  function renderMarks() {
    var m = S.mark;
    $("marks").textContent = m.a == null && m.b == null ? "No range marked. Press I and O at the playhead, or Shift+drag on the timeline."
      : "Marked: " + (m.a == null ? "?" : fmt(m.a)) + " → " + (m.b == null ? "?" : fmt(m.b)) + (m.a != null && m.b != null ? "  (" + (m.b - m.a).toFixed(1) + " s)" : "");
  }
  function renderInfo() {
    var tot = TL.total(S.clips), speed = +$("in-speed").value || 1;
    $("summary").textContent = S.clips.length ? "Timeline " + fmt(tot) + (speed !== 1 ? " → " + fmt(tot / speed) + " at " + speed + "×" : "") + " · " + S.clips.length + " clip" + (S.clips.length > 1 ? "s" : "") : "";
    var c = S.sel >= 0 ? S.clips[S.sel] : null, a = c && assetFor(c.asset);
    $("clip-info").textContent = c && a ? a.name + "  " + fmt(c["in"]) + " → " + fmt(c.out) + "  (" + (c.out - c["in"]).toFixed(1) + " s)" : "No clip selected. Click a clip on the timeline.";
    $("btn-undo").disabled = !S.hist.canUndo(); $("btn-redo").disabled = !S.hist.canRedo();
    ["btn-split", "btn-del", "btn-dup"].forEach(function (id) { $(id).disabled = !S.clips.length; });
    var name = S.projectName || (S.projectPath ? baseName(S.projectPath).replace(/\.vproj\.json$/, "") : "Untitled project");
    $("file-chip").textContent = (S.dirty ? "● " : "") + name; $("file-chip").title = S.projectPath || "Not saved yet";
    $("empty").hidden = S.clips.length > 0;
  }

  // ---------------------------------------------------------------- preview: two video elements, the next clip is preloaded
  var vids = [$("video"), $("video2")], ACT = 0, PB = { i: -1, playing: false };
  function act() { return vids[ACT]; }
  function idle() { return vids[1 - ACT]; }
  function show(v) { vids.forEach(function (x) { x.style.opacity = x === v ? "1" : "0"; x.style.zIndex = x === v ? "2" : "1"; x.muted = x !== v; }); }
  function attach(v, assetId, srcTime, done) {
    var a = assetFor(assetId); if (!a || !a.src) { if (done) done(false); return; }
    function go() { try { v.currentTime = srcTime; } catch (e) { /* not seekable yet */ } if (done) done(true); }
    if (v.getAttribute("data-asset") !== assetId) {
      v.setAttribute("data-asset", assetId);
      var once = function () { v.removeEventListener("loadedmetadata", once); go(); };
      v.addEventListener("loadedmetadata", once); v.src = a.src;
    } else if (v.readyState >= 1) go();
    else { var o2 = function () { v.removeEventListener("loadedmetadata", o2); go(); }; v.addEventListener("loadedmetadata", o2); }
  }
  function invalidatePreload() { idle().removeAttribute("data-for"); }
  function currentHit() { return TL.at(S.clips, S.t); }
  function syncPlayback() {                    // put the active video on the frame under the playhead
    var hit = currentHit();
    if (!hit) { vids.forEach(function (v) { v.pause(); }); PB.i = -1; PB.playing = false; updatePlayIcon(); layoutStage(); return; }
    var a = assetFor(hit.clip.asset); PB.i = hit.index;
    if (!a || !a.src) { busy(a && a.state === "missing" ? "File not found: " + a.name : "Preparing preview…"); return; }
    busy(null);
    var wasPlaying = PB.playing;
    attach(act(), hit.clip.asset, hit.src, function () { show(act()); layoutStage(); if (wasPlaying) act().play(); });
  }
  function seek(t) {
    S.t = clamp(t, 0, TL.total(S.clips)); invalidatePreload();
    var wasPlaying = PB.playing; syncPlayback(); if (!wasPlaying) act().pause();
    drawPlayhead();
  }
  function updatePlayIcon() { $("btn-play").innerHTML = PB.playing ? "&#10074;&#10074;" : "&#9654;"; }
  function togglePlay() {
    if (!S.clips.length) return;
    if (PB.playing) { PB.playing = false; vids.forEach(function (v) { v.pause(); }); updatePlayIcon(); return; }
    if (S.t >= TL.total(S.clips) - 0.05) S.t = 0;
    var hit = currentHit(), a = assetFor(hit.clip.asset); if (!a || !a.src) { busy("Preparing preview…"); return; }
    PB.playing = true; PB.i = hit.index; updatePlayIcon();
    attach(act(), hit.clip.asset, hit.src, function () { show(act()); act().play(); requestAnimationFrame(tick); });
  }
  function tick() {
    if (!PB.playing) return;
    var L = TL.layout(S.clips), item = L.items[PB.i], v = act();
    if (!item) { PB.playing = false; updatePlayIcon(); return; }
    var srcT = v.currentTime;
    S.t = item.start + (srcT - item.clip["in"]);
    var next = S.clips[PB.i + 1], contiguous = next && next.asset === item.clip.asset && Math.abs(next["in"] - item.clip.out) < 0.06;
    if (next && !contiguous && item.clip.out - srcT < 1.2 && idle().getAttribute("data-for") !== next.id) {
      idle().setAttribute("data-for", next.id); idle().pause(); attach(idle(), next.asset, next["in"]);
    }
    if (srcT >= item.clip.out - 0.03 || v.ended) {
      if (!next) { PB.playing = false; vids.forEach(function (x) { x.pause(); }); S.t = L.total; updatePlayIcon(); drawPlayhead(); return; }
      PB.i += 1;
      if (contiguous) { /* same file continues: nothing to switch */ }
      else if (idle().getAttribute("data-for") === next.id && idle().readyState >= 2) { v.pause(); ACT = 1 - ACT; show(act()); act().play(); }
      else attach(v, next.asset, next["in"], function () { act().play(); });
    }
    drawPlayhead();
    requestAnimationFrame(tick);
  }
  vids.forEach(function (v) { v.addEventListener("loadedmetadata", layoutStage); v.addEventListener("click", togglePlay); });
  $("btn-play").addEventListener("click", togglePlay);

  // ---------------------------------------------------------------- stage / guide
  function layoutStage() {
    var wrap = $("stage-wrap"), tr = $("transport").offsetHeight, v = act();
    var hit = currentHit(), a = hit && assetFor(hit.clip.asset), vi = a && a.info && a.info.video;
    var ar = (v.videoWidth && v.videoHeight && v.getAttribute("data-asset")) ? v.videoWidth / v.videoHeight : (vi ? vi.display_width / vi.display_height : 16 / 9);
    var maxW = wrap.clientWidth - 24, maxH = wrap.clientHeight - tr - 24;
    var w = Math.min(maxW, maxH * ar), h = w / ar;
    var st = $("stage"); st.style.width = Math.max(100, w) + "px"; st.style.height = Math.max(60, h) + "px";
    updateGuide();
  }
  function updateGuide() {
    var g = $("frame-guide"), mode = $("in-reframe").value, st = $("stage");
    $("anchor-wrap").hidden = mode.indexOf("crop_") !== 0;
    if (mode.indexOf("crop_") !== 0) { g.hidden = true; return; }
    var m = { crop_9x16: 9 / 16, crop_1x1: 1, crop_4x5: 4 / 5, crop_16x9: 16 / 9 }[mode];
    var W = st.clientWidth, H = st.clientHeight, ar = W / H, w, h, x, y;
    if (ar > m) { h = H; w = H * m; } else { w = W; h = W / m; }
    x = (W - w) / 2; y = (H - h) / 2;
    if (w < W - 1 && ({ left: 0, right: W - w })[S.anchor] != null) x = ({ left: 0, right: W - w })[S.anchor];
    if (h < H - 1 && ({ top: 0, bottom: H - h })[S.anchor] != null) y = ({ top: 0, bottom: H - h })[S.anchor];
    g.hidden = false; g.style.left = x + "px"; g.style.top = y + "px"; g.style.width = w + "px"; g.style.height = h + "px";
  }
  window.addEventListener("resize", function () { layoutStage(); drawAll(); });

  // ---------------------------------------------------------------- timeline
  function total() { return TL.total(S.clips); }
  function trackWidth() { return Math.max($("tl-scroll").clientWidth, Math.ceil((total() || 1) * S.zoom)); }
  function fit() { S.zoom = Math.max(2, ($("tl-scroll").clientWidth - 2) / (total() || 1)); renderAll(); $("tl-scroll").scrollLeft = 0; }
  function zoomBy(f) {
    var sc = $("tl-scroll"), centre = (sc.scrollLeft + sc.clientWidth / 2) / S.zoom;
    S.zoom = clamp(S.zoom * f, 2, 2000); renderAll(); sc.scrollLeft = centre * S.zoom - sc.clientWidth / 2;
  }
  $("btn-zoom-in").addEventListener("click", function () { zoomBy(1.5); });
  $("btn-zoom-out").addEventListener("click", function () { zoomBy(1 / 1.5); });
  $("btn-zoom-fit").addEventListener("click", fit);
  $("tl-scroll").addEventListener("wheel", function (e) { if (e.ctrlKey) { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.2 : 1 / 1.2); } }, { passive: false });
  $("tl-scroll").addEventListener("scroll", drawCanvases);
  function sizeTrack() { var w = trackWidth(); $("track").style.width = w + "px"; return w; }

  function drawCanvases() {
    var sc = $("tl-scroll"), vw = sc.clientWidth, dpr = window.devicePixelRatio || 1, x0 = sc.scrollLeft;
    [["ruler", 26], ["wave", 110]].forEach(function (p) {
      var c = $(p[0]); c.width = vw * dpr; c.height = p[1] * dpr; c.style.width = vw + "px"; c.style.height = p[1] + "px";
      c.style.left = x0 + "px"; c.style.right = "auto";
      var g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, vw, p[1]);
    });
    var g = $("ruler").getContext("2d"), step = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find(function (s) { return s * S.zoom >= 70; }) || 600;
    g.fillStyle = cssColor("--muted", "#8a94a8"); g.font = "11px ui-monospace, monospace"; g.strokeStyle = cssColor("--line", "#3a4560");
    for (var t = Math.floor(x0 / S.zoom / step) * step; t * S.zoom - x0 < vw + 80; t += step) {
      var x = Math.round(t * S.zoom - x0) + 0.5; g.beginPath(); g.moveTo(x, 14); g.lineTo(x, 26); g.stroke();
      g.fillText(fmt(t, step < 1), x + 4, 12);
    }
    // audio lane: waveform of every clip, mapped from timeline time back to the source file
    var w = $("wave").getContext("2d"), H = 110, mid = H / 2, amp = mid - 6, col = cssColor("--teal", "#4ecdc4");
    var L = TL.layout(S.clips), top = new Array(vw), px, any = false;
    for (px = 0; px < vw; px++) top[px] = 0;
    L.items.forEach(function (it) {
      var a = assetFor(it.clip.asset), x1 = it.start * S.zoom - x0, x2 = it.end * S.zoom - x0;
      if (x2 < 0 || x1 > vw || !a || !a.peaks || !a.peaks.length || !a.dur) return;
      any = true;
      var per = a.peaks.length / a.dur;
      for (px = Math.max(0, Math.floor(x1)); px < Math.min(vw, Math.ceil(x2)); px++) {
        var ta = it.clip["in"] + ((x0 + px) / S.zoom - it.start), tb = ta + 1 / S.zoom;
        var ia = Math.floor(ta * per), ib = Math.max(ia + 1, Math.ceil(tb * per)), m = 0, sum = 0, n = 0;
        for (var i = Math.max(0, ia); i < ib && i < a.peaks.length; i++) { if (a.peaks[i] > m) m = a.peaks[i]; sum += a.peaks[i]; n++; }
        top[px] = n ? Math.pow(0.65 * m + 0.35 * (sum / n), 0.85) : 0;
      }
    });
    if (any) {
      var sm = top.map(function (v, k) { return (top[Math.max(0, k - 1)] + 2 * v + top[Math.min(vw - 1, k + 1)]) / 4; });
      w.globalAlpha = 0.28; w.fillStyle = col; w.fillRect(0, mid - 0.5, vw, 1); w.globalAlpha = 1;
      w.beginPath(); w.moveTo(0, mid);
      for (px = 0; px < vw; px++) w.lineTo(px, mid - Math.max(sm[px] > 0 ? 1 : 0, sm[px] * amp));
      w.lineTo(vw, mid);
      for (px = vw - 1; px >= 0; px--) w.lineTo(px, mid + Math.max(sm[px] > 0 ? 1 : 0, sm[px] * amp));
      w.closePath(); w.globalAlpha = 0.9; w.fillStyle = col; w.fill(); w.globalAlpha = 1; w.lineWidth = 1; w.strokeStyle = col; w.stroke();
    } else if (S.clips.length) {
      w.fillStyle = cssColor("--muted", "#8a94a8"); w.font = "12px system-ui"; w.fillText("Reading audio… (clips without sound show no waveform)", 12, mid);
    }
    w.strokeStyle = cssColor("--line", "#3a4560"); w.lineWidth = 1;       // clip boundaries across the audio lane
    L.items.forEach(function (it) { var bx = Math.round(it.end * S.zoom - x0) + 0.5; if (bx > 0 && bx < vw) { w.beginPath(); w.moveTo(bx, 4); w.lineTo(bx, H - 4); w.stroke(); } });
  }

  function drawClips() {
    var box = $("clips"); box.textContent = "";
    TL.layout(S.clips).items.forEach(function (it, i) {
      var a = assetFor(it.clip.asset), d = el("div", "clip" + (i === S.sel ? " sel" : "") + (a && a.state === "missing" ? " missing" : ""));
      d.style.left = (it.start * S.zoom) + "px"; d.style.width = Math.max(4, it.dur * S.zoom - 1) + "px"; d.setAttribute("data-i", i);
      if (a && a.thumbs && a.dur) {
        var n = a.thumbs.count, span = a.dur / n, src = url("/api/cache", { id: a.cacheId, name: a.thumbs.name });
        for (var j = Math.floor(it.clip["in"] / span); j < Math.ceil(it.clip.out / span) && j < n; j++) {
          var tile = document.createElement("i");
          tile.style.left = ((j * span - it.clip["in"]) * S.zoom) + "px"; tile.style.width = (span * S.zoom + 1) + "px";
          tile.style.backgroundImage = "url('" + src + "')"; tile.style.backgroundSize = (n * 100) + "% 100%";
          tile.style.backgroundPosition = (n > 1 ? j / (n - 1) * 100 : 0) + "% 0"; d.appendChild(tile);
        }
      }
      d.appendChild(el("span", "label", (a ? a.name : "?") + (a && a.state === "missing" ? " (file missing)" : "")));
      var hl = el("b", "h l"), hr = el("b", "h r"); hl.setAttribute("data-edge", "left"); hr.setAttribute("data-edge", "right"); d.appendChild(hl); d.appendChild(hr);
      box.appendChild(d);
    });
    var mr = $("mark-range"), a1 = S.mark.a, b1 = S.mark.b;
    if (a1 != null || b1 != null) { var s0 = a1 != null ? a1 : b1, e0 = b1 != null ? b1 : a1; mr.hidden = false; mr.style.left = (s0 * S.zoom) + "px"; mr.style.width = Math.max(2, (e0 - s0) * S.zoom) + "px"; }
    else mr.hidden = true;
  }
  function drawPlayhead() {
    $("playhead").style.left = (S.t * S.zoom) + "px";
    $("time").textContent = fmt(S.t) + " / " + fmt(total());
    var sc = $("tl-scroll"), x = S.t * S.zoom;
    if (PB.playing && (x < sc.scrollLeft || x > sc.scrollLeft + sc.clientWidth - 40)) sc.scrollLeft = x - 60;
  }
  function drawAll() { sizeTrack(); drawCanvases(); drawClips(); drawPlayhead(); }
  function renderAll() { renderMarks(); renderInfo(); drawAll(); }

  // mouse on the timeline: click/drag empty space = scrub, Shift+drag = mark a range, drag a clip = reorder, drag an edge = trim
  (function () {
    var drag = null;
    function tAt(e) { var r = $("track").getBoundingClientRect(); return clamp((e.clientX - r.left) / S.zoom, 0, total()); }
    $("track").addEventListener("mousedown", function (e) {
      if (e.button !== 0 || !S.clips.length) return;
      var clipEl = e.target.closest ? e.target.closest(".clip") : null;
      if (clipEl && !e.shiftKey) {
        var i = +clipEl.getAttribute("data-i"), edge = e.target.getAttribute && e.target.getAttribute("data-edge");
        S.sel = i; seek(tAt(e));
        drag = { kind: edge ? "trim" : "move", i: i, edge: edge, x0: e.clientX, base: S.clips, moved: false };
        renderAll(); e.preventDefault(); return;
      }
      drag = { kind: e.shiftKey ? "mark" : "scrub", t0: tAt(e) };
      if (drag.kind === "scrub") { S.sel = -1; seek(drag.t0); renderAll(); }
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return;
      if (drag.kind === "scrub") seek(tAt(e));
      else if (drag.kind === "mark") { var t = tAt(e); S.mark = { a: Math.min(drag.t0, t), b: Math.max(drag.t0, t) }; renderAll(); }
      else if (drag.kind === "trim") {
        var dx = (e.clientX - drag.x0) / S.zoom, a = assetFor(drag.base[drag.i].asset);
        if (Math.abs(dx) < 0.001 && !drag.moved) return;
        drag.moved = true; S.clips = TL.trim(drag.base, drag.i, drag.edge, dx, a && a.dur); S.dirty = true; invalidatePreload();
        S.t = clamp(S.t, 0, total()); renderAll();
      } else if (drag.kind === "move") {
        if (!drag.moved && Math.abs(e.clientX - drag.x0) < 5) return;
        drag.moved = true; var di = TL.dropIndex(drag.base, drag.i, tAt(e)); drag.to = di;
        var others = TL.layout(drag.base.filter(function (_, k) { return k !== drag.i; })), px = di < others.items.length ? others.items[di].start : others.total;
        $("drop-ind").hidden = false; $("drop-ind").style.left = (px * S.zoom) + "px";
      }
    });
    window.addEventListener("mouseup", function () {
      if (!drag) return;
      var d = drag; drag = null; $("drop-ind").hidden = true;
      if (d.kind === "trim" && d.moved) { S.hist.push({ clips: d.base, sel: d.i }); afterEdit(); }
      else if (d.kind === "move" && d.moved && d.to !== d.i) { S.clips = d.base; edit(function (c) { S.sel = d.to; return TL.move(c, d.i, d.to); }); }
    });
  })();

  // ---------------------------------------------------------------- keyboard
  window.addEventListener("keydown", function (e) {
    if (/INPUT|SELECT|TEXTAREA/.test((e.target.tagName || "")) && e.target.type !== "range" && e.target.type !== "checkbox") return;
    if (!$("modal").hidden) { if (e.key === "Escape") closeDialog(); return; }
    var k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey, a = S.clips[0] && assetFor(S.clips[0].asset), fps = (a && a.info && a.info.video && a.info.video.fps) || 25;
    if (mod && k === "z") { e.preventDefault(); if (e.shiftKey) redo(); else undo(); }
    else if (mod && k === "y") { e.preventDefault(); redo(); }
    else if (mod && k === "s") { e.preventDefault(); saveProject(false); }
    else if (mod) return;
    else if (k === " ") { e.preventDefault(); togglePlay(); }
    else if (k === "s") doSplit();
    else if (k === "i") setIn();
    else if (k === "o") setOut();
    else if (k === "x") cutRange();
    else if (k === "arrowleft") { e.preventDefault(); seek(S.t - (e.shiftKey ? 1 : 1 / fps)); }
    else if (k === "arrowright") { e.preventDefault(); seek(S.t + (e.shiftKey ? 1 : 1 / fps)); }
    else if (k === "arrowup" || k === "arrowdown") {
      e.preventDefault(); var L = TL.layout(S.clips), pts = [0].concat(L.items.map(function (it) { return it.end; }));
      var tgt = k === "arrowup" ? pts.filter(function (p) { return p < S.t - 0.05; }).pop() : pts.filter(function (p) { return p > S.t + 0.05; })[0];
      seek(tgt != null ? tgt : (k === "arrowup" ? 0 : L.total));
    }
    else if (k === "home") seek(0);
    else if (k === "end") seek(total());
    else if (k === "delete" || k === "backspace") doDelete();
    else if (k === "+" || k === "=") zoomBy(1.5);
    else if (k === "-") zoomBy(1 / 1.5);
  });

  // ---------------------------------------------------------------- projects (save / open)
  function projectData() {
    var used = {}; S.clips.forEach(function (c) { used[c.asset] = true; });
    var assets = {}; Object.keys(used).forEach(function (id) { var a = S.assets[id]; if (a) assets[id] = { path: a.path, name: a.name }; });
    return { version: 1, name: S.projectName || "", assets: assets, clips: S.clips.map(function (c) { return { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; }) };
  }
  function saveProject(forceDialog) {
    if (!S.clips.length) { flash("Nothing to save yet."); return; }
    if (S.projectPath && !forceDialog) return doSave(S.projectPath);
    openDialog({ kind: "project", save: true, title: "Save project", done: doSave });
  }
  function doSave(path) {
    var name = baseName(path).replace(/\.vproj\.json$/, "").replace(/\.json$/, "");
    S.projectName = S.projectName || name;
    api("/api/project/save", null, { path: path, project: projectData() }).then(function (r) { S.projectPath = r.path; S.dirty = false; renderInfo(); flash("Saved " + baseName(r.path)); })
      .catch(function (e) { flash("Could not save: " + e.message + (e.hint ? " - " + e.hint : "")); });
  }
  function loadProjectFile(path) {
    busy("Opening project…");
    api("/api/project/load", { path: path }).then(function (p) {
      S.assets = {}; S.clips = []; S.sel = -1; S.t = 0; S.mark = { a: null, b: null }; S.hist = TL.createHistory(100);
      var ids = Object.keys(p.assets);
      return Promise.all(ids.map(function (id) { return registerAsset(id, p.assets[id].path, p.assets[id].name).catch(function () { return null; }); })).then(function () {
        S.clips = p.clips.map(function (c) { return { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; });
        S.projectPath = p.path; S.projectName = p.name || ""; S.dirty = false; S.fitted = true; S.sel = S.clips.length ? 0 : -1;
        busy(null); invalidatePreload(); syncPlayback(); renderAll(); fit();
        var missing = ids.filter(function (id) { return S.assets[id] && S.assets[id].state === "missing"; });
        if (missing.length) flash(missing.length + " file(s) of this project were not found. They show as red clips.");
      });
    }).catch(function (e) { busy("Could not open the project: " + e.message + (e.hint ? " (" + e.hint + ")" : "")); });
  }
  $("btn-save").addEventListener("click", function () { saveProject(false); });
  $("btn-saveas").addEventListener("click", function () { saveProject(true); });

  // ---------------------------------------------------------------- export
  $("btn-export").addEventListener("click", function () {
    if (!S.clips.length) { openDialog(); return; }
    var body = {
      clips: TL.forExport(S.clips, S.assets), speed: +$("in-speed").value, reframe: $("in-reframe").value, anchor: S.anchor,
      loudness: $("in-loud").checked ? +$("in-lufs").value : null, preset: $("in-preset").value || null,
      output_dir: $("in-outdir").value.trim() || null,
    };
    var btn = this; btn.disabled = true; $("result").hidden = true; $("job").hidden = false; $("job-bar").style.width = "4%"; $("job-step").textContent = "Starting…";
    api("/api/export", null, body).then(function (r) { pollExport(r.job, btn); })
      .catch(function (e) { btn.disabled = false; $("job").hidden = true; showResult({ error: e.message, hint: e.hint }); });
  });
  function pollExport(id, btn) {
    (function tick() {
      api("/api/job", { id: id }).then(function (j) {
        $("job-bar").style.width = Math.max(4, Math.round(j.progress * 100)) + "%"; $("job-step").textContent = j.step ? j.step + "…" : "Working…";
        if (j.state === "running") return setTimeout(tick, 600);
        btn.disabled = false; $("job").hidden = true;
        if (j.state === "error") showResult({ error: j.error.error, hint: j.error.hint }); else showResult(null, j.result);
      }).catch(function (e) { btn.disabled = false; $("job").hidden = true; showResult({ error: e.message }); });
    })();
  }
  function showResult(err, r) {
    var box = $("result"); box.hidden = false; box.textContent = "";
    if (err) { box.appendChild(el("div", "bad", "Export failed")); box.appendChild(el("div", "", err.error + (err.hint ? " - " + err.hint : ""))); return; }
    box.appendChild(el("div", "ok", "Done ✓"));
    box.appendChild(el("div", "", r.output));
    box.appendChild(el("div", "muted", fmt(r.duration_s || 0) + " · " + (r.size_bytes / 1048576).toFixed(1) + " MB · " + r.steps.join(" → ")));
    var row = el("div", "row"), add = el("button", "btn small", "Add result to timeline"); add.addEventListener("click", function () { addClipFromPath(r.output); }); row.appendChild(add); box.appendChild(row);
    if (r.platform_check) {
      var pc = r.platform_check; box.appendChild(el("div", pc.passed ? "ok" : "bad", pc.label + ": " + (pc.passed ? "all checks passed" : "needs fixes")));
      var ul = el("ul");
      pc.checks.forEach(function (c) { ul.appendChild(el("li", c.status, (c.status === "pass" ? "✓ " : c.status === "fail" ? "✗ " : "! ") + c.check + ": " + c.value + (c.status !== "pass" && c.fix ? "  - " + c.fix : ""))); });
      box.appendChild(ul);
    }
  }

  // ---------------------------------------------------------------- drag & drop (browsers hide real paths, so dropped files are copied in)
  (function () {
    var depth = 0, queue = [], working = false;
    function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0; }
    function next() {
      if (working || !queue.length) return;
      working = true; var f = queue.shift(), left = queue.length;
      busy("Copying “" + f.name + "” into the editor… 0%" + (left ? "  (" + left + " more waiting)" : ""));
      var xhr = new XMLHttpRequest();
      xhr.open("POST", url("/api/upload", { name: f.name }));
      xhr.upload.onprogress = function (ev) { if (ev.lengthComputable) busy("Copying “" + f.name + "” into the editor… " + Math.round(ev.loaded / ev.total * 100) + "%" + (left ? "  (" + left + " more waiting)" : "")); };
      xhr.onload = function () {
        var j = {}; try { j = JSON.parse(xhr.responseText); } catch (x) { /* keep empty */ }
        var done = function () { working = false; next(); };
        if (xhr.status === 200 && j.path) addClipFromPath(j.path, true).then(done, done);
        else { busy("Could not use that file: " + (j.error || "upload failed") + (j.hint ? " (" + j.hint + ")" : "")); done(); }
      };
      xhr.onerror = function () { busy("Upload failed. Use Add clip… instead."); working = false; next(); };
      xhr.send(f);
    }
    window.addEventListener("dragenter", function (e) { if (hasFiles(e)) { depth++; document.body.classList.add("drop-on"); e.preventDefault(); } });
    window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener("dragleave", function () { depth = Math.max(0, depth - 1); if (!depth) document.body.classList.remove("drop-on"); });
    window.addEventListener("drop", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth = 0; document.body.classList.remove("drop-on");
      Array.prototype.forEach.call(e.dataTransfer.files || [], function (f) { queue.push(f); }); next();
    });
  })();

  // ---------------------------------------------------------------- all tools (forms generated from the tool schemas)
  var T = { tools: null, cur: null, fields: {}, job: 0 };
  var PATHISH = { input: "media", input2: "media", pip_input: "media", audio: "media", music: "media", image: "image",
    captions: "captions", font_file: "font", model_path: "folder", output_dir: "folder", output: "media" };
  var HIDE = { input: 1, output: 1, output_dir: 1, overwrite: 1, timeout_s: 1, crf: 1 };
  var ADV = { output: 1, output_dir: 1, overwrite: 1, timeout_s: 1, crf: 1 };

  function loadTools() {
    if (T.tools) return;
    api("/api/tools").then(function (r) { T.tools = r; renderToolList(); }).catch(function (e) { $("tool-list").textContent = e.message; });
  }
  function renderToolList() {
    var q = $("tool-search").value.trim().toLowerCase(), box = $("tool-list"); box.textContent = "";
    var n = 0;
    T.tools.groups.forEach(function (g) {
      var items = T.tools.tools.filter(function (t) { return t.group === g && (!q || (t.name + " " + t.description).toLowerCase().indexOf(q) >= 0); });
      if (!items.length) return;
      box.appendChild(el("h3", "", g + " (" + items.length + ")"));
      items.forEach(function (t) {
        n++;
        var b = el("button", "tool-item"); b.setAttribute("data-tool", t.name);
        b.appendChild(el("span", "tag", t.read_only ? "reads" : "makes file"));
        b.appendChild(el("b", "", t.name.replace(/^ve_/, "")));
        b.appendChild(el("small", "", t.description.split(". ")[0].slice(0, 110)));
        b.addEventListener("click", function () { openTool(t); });
        box.appendChild(b);
      });
    });
    if (!n) box.appendChild(el("div", "muted", "No tool matches."));
  }
  $("tool-search").addEventListener("input", function () { if (T.tools) renderToolList(); });
  document.querySelector('#tabs button[data-tab="tools"]').addEventListener("click", loadTools);
  $("tool-back").addEventListener("click", function () { $("tool-form").hidden = true; $("tool-list").hidden = false; $("tool-search").hidden = false; });

  function field(name, p, required, host) {
    var wrap = el("div", "fld"), lab = el("label", "", name.replace(/_/g, " ") + (required ? " *" : ""));
    wrap.appendChild(lab); var input, kind = PATHISH[name], types = [].concat(p.type);
    if (p.enum) {
      input = document.createElement("select"); var o0 = el("option", "", p.default !== undefined ? "(default: " + p.default + ")" : "(choose)"); o0.value = ""; input.appendChild(o0);
      p.enum.forEach(function (v) { var o = el("option", "", String(v)); o.value = String(v); input.appendChild(o); });
      T.fields[name] = function () { return input.value === "" ? undefined : (types.indexOf("integer") >= 0 || types.indexOf("number") >= 0 ? Number(input.value) : input.value); };
    } else if (types.indexOf("boolean") >= 0) {
      input = document.createElement("input"); input.type = "checkbox"; input.checked = !!p.default; lab.className = "check"; lab.textContent = ""; lab.appendChild(input);
      lab.appendChild(document.createTextNode(" " + name.replace(/_/g, " ") + (p.default ? " (default on)" : "")));
      T.fields[name] = function () { return input.checked === !!p.default ? undefined : input.checked; };
      wrap.removeChild(lab); wrap.appendChild(lab); host.appendChild(wrap); if (p.description) wrap.appendChild(el("div", "hint", p.description)); return;
    } else if (types.indexOf("array") >= 0) {
      input = document.createElement("textarea");
      var ex = name === "segments" ? "one range per line, e.g. 00:05 - 00:08" : name === "inputs" ? "one file path per line, in play order" : "one value per line (or comma separated)";
      input.placeholder = ex;
      T.fields[name] = function () {
        var raw = input.value.trim(); if (!raw) return undefined;
        var lines = raw.split(/\n/).map(function (l) { return l.trim(); }).filter(Boolean);
        if (name === "segments") return lines.map(function (l) { var m = l.split(/\s*(?:-|→|–|to)\s*/); return { start: m[0], end: m[1] }; });
        if (name === "inputs") return lines;
        return raw.split(/[\n,]/).map(function (x) { return x.trim(); }).filter(Boolean).map(function (x) { return isNaN(Number(x)) ? x : Number(x); });
      };
    } else {
      input = document.createElement("input"); input.type = (types.indexOf("integer") >= 0 || types.indexOf("number") >= 0) && types.indexOf("string") < 0 ? "number" : "text";
      if (input.type === "number") { input.step = types.indexOf("integer") >= 0 ? "1" : "any"; if (p.minimum != null) input.min = p.minimum; if (p.maximum != null) input.max = p.maximum; }
      if (p.default !== undefined) input.placeholder = String(p.default);
      if (name === "text") { input = document.createElement("textarea"); }
      T.fields[name] = function () {
        var v = input.value.trim(); if (v === "") return undefined;
        return input.type === "number" ? Number(v) : v;
      };
      if (kind) {
        var row = el("div", "inline"); row.appendChild(input);
        var btn = el("button", "btn small", "Browse…"); btn.type = "button";
        btn.addEventListener("click", function () { openDialog({ kind: kind === "folder" ? "media" : kind, folder: kind === "folder", done: function (v) { input.value = v; } }); });
        row.appendChild(btn); wrap.appendChild(row);
        if (p.description) wrap.appendChild(el("div", "hint", p.description)); host.appendChild(wrap); return;
      }
    }
    wrap.appendChild(input);
    if (p.description) wrap.appendChild(el("div", "hint", p.description));
    host.appendChild(wrap);
  }

  function openTool(t) {
    T.cur = t; T.fields = {};
    $("tool-list").hidden = true; $("tool-search").hidden = true; $("tool-form").hidden = false;
    $("tool-title").textContent = t.name; $("tool-desc").textContent = t.description;
    $("tool-fields").textContent = ""; $("tool-adv").textContent = ""; $("tool-result").hidden = true; $("tool-job").hidden = true;
    var usesInput = !!t.properties.input;
    if (usesInput) {
      var f = el("div", "fld"); f.appendChild(el("label", "", "input"));
      var row = el("div", "inline"), cur = el("input"); cur.type = "text"; cur.id = "tool-input"; cur.value = currentPath(); cur.placeholder = "Open a video first, or browse";
      var br = el("button", "btn small", "Browse…"); br.addEventListener("click", function () { openDialog({ kind: "media", done: function (v) { cur.value = v; } }); });
      row.appendChild(cur); row.appendChild(br); f.appendChild(row); $("tool-fields").appendChild(f);
      T.fields.input = function () { return cur.value.trim() || undefined; };
    }
    Object.keys(t.properties).forEach(function (name) {
      if (name === "input") return;
      field(name, t.properties[name], t.required.indexOf(name) >= 0, ADV[name] ? $("tool-adv") : $("tool-fields"));
    });
    $("tool-run").disabled = false;
  }

  $("tool-run").addEventListener("click", function () {
    var t = T.cur, args = {}, btn = this;
    Object.keys(T.fields).forEach(function (k) { var v = T.fields[k](); if (v !== undefined) args[k] = v; });
    btn.disabled = true; $("tool-result").hidden = true; $("tool-job").hidden = false; $("tool-bar").style.width = "10%"; $("tool-step").textContent = "Running…";
    var mine = ++T.job, started = Date.now();
    api("/api/tool", null, { name: t.name, args: args }).then(function (r) {
      (function tick() {
        api("/api/job", { id: r.job }).then(function (j) {
          if (mine !== T.job) return;
          $("tool-bar").style.width = Math.min(90, 10 + (Date.now() - started) / 400) + "%";
          if (j.state === "running") return setTimeout(tick, 600);
          btn.disabled = false; $("tool-job").hidden = true;
          if (j.state === "error") showToolResult(t, null, j.error); else showToolResult(t, j.result);
        }).catch(function (e) { btn.disabled = false; $("tool-job").hidden = true; showToolResult(t, null, { error: e.message }); });
      })();
    }).catch(function (e) { btn.disabled = false; $("tool-job").hidden = true; showToolResult(t, null, { error: e.message, hint: e.hint }); });
  });

  function showToolResult(t, r, err) {
    var box = $("tool-result"); box.hidden = false; box.textContent = "";
    if (err) { box.appendChild(el("div", "bad", "Failed")); box.appendChild(el("div", "", err.error + (err.hint ? " - " + err.hint : ""))); return; }
    box.appendChild(el("div", "ok", "Done ✓"));
    if (r.output) {
      box.appendChild(el("div", "", r.output));
      box.appendChild(el("div", "muted", (r.duration_s != null ? fmt(r.duration_s) + " · " : "") + (r.info && r.info.size_bytes ? (r.info.size_bytes / 1048576).toFixed(1) + " MB" : "")));
      if (/\.(mp4|mov|m4v|mkv|webm|avi|mp3|wav|m4a|flac)$/i.test(r.output)) {
        var row = el("div", "row"), b = el("button", "btn small", "Add result to timeline");
        b.addEventListener("click", function () { loadFile(r.output); }); row.appendChild(b); box.appendChild(row);
      }
      if (r.info && r.info.outputs && r.info.outputs.length > 1) box.appendChild(el("pre", "", r.info.outputs.join("\n")));
    }
    var show = r.info && (!r.output || t.read_only) ? r.info : null;
    if (show) box.appendChild(el("pre", "", JSON.stringify(show, null, 2)));
  }

  // ---------------------------------------------------------------- "Powered by" link
  // Inside Hermes Desktop the page runs in a sandboxed frame without popups: ask the embedding page to open the link.
  $("powered").addEventListener("click", function (e) {
    if (window.parent !== window) { e.preventDefault(); window.parent.postMessage({ type: "ve-open-link", url: this.href }, "*"); }
  });

  // ---------------------------------------------------------------- start
  window.__ve = { seek: seek, state: S, TL: TL };          // handy for debugging and the browser tests
  function init() {
    api("/api/config").then(function (c) {
      S.config = c;
      var sp = $("in-speed"); c.speeds.forEach(function (v) { var o = el("option", "", v + "×" + (v === 1 ? " (normal)" : "")); o.value = v; if (v === 1) o.selected = true; sp.appendChild(o); });
      var pr = $("in-preset"); var none = el("option", "", "No preset (keep as is)"); none.value = ""; pr.appendChild(none);
      c.presets.forEach(function (p) { var o = el("option", "", p); o.value = p; pr.appendChild(o); });
      var open = Q.get("open"), proj = Q.get("project");
      if (proj) loadProjectFile(proj); else if (open) addClipFromPath(open); else fillRecent($("recent"), $("recent-title"), null);
      $("in-outdir").placeholder = "Same folder as the first clip";
      layoutStage(); renderAll();
    }).catch(function (e) { busy("Cannot reach the editor server: " + e.message); });
  }
  show(vids[0]); layoutStage(); renderAll(); init();
})();
