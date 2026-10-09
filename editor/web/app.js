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
    projectPath: null, projectName: "", dirty: false, config: null, dlgPath: "", fitted: false,
    canvas: { aspect: "auto", short: 1080 }, bg: { mode: "blur", color: "#000000", color2: "#1b1464", image: "" },
    texts: [], audios: [], overlays: [], shapes: [], scenes: [], bgs: [], tracks: { scene: 1, bg: 1, shape: 1, text: 1, overlay: 1, audio: 1 },
    selText: -1, selAudio: -1, selOv: -1, selShape: -1, selScene: -1, selBg: -1, magnet: true,           // layers: text on the picture, audio items (music, voice-over)
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
  function busy(msg) { var o = $("overlay"); o.hidden = !msg; o.textContent = msg || ""; }

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
  $("in-speed").addEventListener("change", renderInfo);

  // ---------------------------------------------------------------- file dialog (add clips / open + save projects / pick files for tools)
  var PICK = null;   // {kind, folder, save, title, done} while the dialog is used for something other than adding a clip
  function openDialog(pick) {
    PICK = pick && pick.kind ? pick : null;
    $("modal").hidden = false;
    $("dlg-usefolder").hidden = !(PICK && (PICK.folder || PICK.save)); $("dlg-mk").hidden = !(PICK && (PICK.folder || PICK.save)); $("dlg-newfolder").value = "";
    $("dlg-usefolder").textContent = PICK && PICK.save ? "Save here" : "Use this folder";
    $("dlg-name").hidden = !(PICK && PICK.save); if (PICK && PICK.save) $("dlg-name").value = S.projectName || "my-project";
    $("dlg-title").textContent = PICK && PICK.title ? PICK.title : "Add a video";
    $("dlg-hint").textContent = !PICK ? "Pick a video or audio file. It is added to the end of the timeline."
      : PICK.kind === "project" && PICK.save ? "Choose a folder and a name. Saves clips, cuts, canvas, texts, audio and overlays (not the media files)."
      : PICK.kind === "project" ? "Pick a saved project (.vproj.json). It replaces what is on the timeline now. Only project files are listed."
      : PICK.folder ? "Pick a folder." : "Pick a file.";
    var isProject = !!(PICK && PICK.kind === "project");               // projects remember their own folder, separate from the media folder
    var start = isProject ? S.dlgProjectPath : S.dlgPath;
    if (PICK && PICK.folder && !PICK.start) start = S.dlgFolderPath || (S.clips[0] && assetFor(S.clips[0].asset) ? dirName(assetFor(S.clips[0].asset).path) : "") || start;
    if (PICK && PICK.save && !start) start = (S.projectPath ? dirName(S.projectPath) : "") || (S.clips[0] && assetFor(S.clips[0].asset) ? dirName(assetFor(S.clips[0].asset).path) : "");   // next to the video
    if (!start && !isProject) start = store("ve.dir");
    if (isProject && !start) {
      api("/api/recent", { kind: "project" }).then(function (r) { browse(r.files.length ? r.files[0].path.replace(/[\\/][^\\/]*$/, "") : ""); }).catch(function () { browse(""); });
    } else browse(start || "");
    var show = !PICK || (isProject && !PICK.save); $("dlg-recent").hidden = !show; if (!show) $("dlg-recent-title").hidden = true;
    $("dlg-recent-title").textContent = isProject ? "Recent projects" : "Recent";
    if (show) fillRecent($("dlg-recent"), $("dlg-recent-title"), closeDialog, isProject);
  }
  function fillRecent(list, title, after, projects) {
    api("/api/recent", projects ? { kind: "project" } : {}).then(function (r) {
      list.textContent = ""; title.hidden = !r.files.length;
      r.files.slice(0, 6).forEach(function (f) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", (projects ? "📄 " : "🎬 ") + f.name.replace(/\.vproj\.json$/, ""))); it.title = f.path;
        it.addEventListener("click", function () { if (after) after(); if (projects) loadProjectFile(f.path); else addClipFromPath(f.path); }); list.appendChild(it);
      });
    }).catch(function () { title.hidden = true; });
  }
  function closeDialog() { $("modal").hidden = true; }
  function browse(path) {
    $("dlg-err").textContent = "";
    var q = path ? { path: path } : {}; if (PICK && PICK.kind) q.kind = PICK.kind;
    api("/api/ls", q).then(function (d) {
      if (PICK && PICK.kind === "project") S.dlgProjectPath = d.path; else if (PICK && PICK.folder) S.dlgFolderPath = d.path; else { S.dlgPath = d.path; store("ve.dir", d.path); }
      $("dlg-path").value = d.path;
      var list = $("dlg-list"); list.textContent = "";
      if (d.parent) { var up = el("div", "item", ".. (up)"); up.addEventListener("click", function () { browse(d.parent); }); list.appendChild(up); }
      d.dirs.forEach(function (x) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", "📁 " + x.name));
        it.addEventListener("click", function () { browse(d.path + sep(d.path) + x.name); }); list.appendChild(it);
      });
      (PICK && (PICK.folder || PICK.save) && PICK.kind !== "project" ? [] : d.files).forEach(function (x) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", (PICK && PICK.kind === "project" ? "📄 " : "🎬 ") + x.name));
        it.appendChild(el("span", "muted", (x.size / 1048576).toFixed(1) + " MB"));
        it.addEventListener("click", function () {
          var full = d.path + sep(d.path) + x.name; closeDialog();
          if (PICK) { if (PICK.done) PICK.done(full); } else addClipFromPath(full);
        }); list.appendChild(it);
      });
      if (!d.files.length && PICK && PICK.kind === "project" && !PICK.save) list.appendChild(el("div", "muted", "No project files in this folder. Save your work with Save, then it shows up here."));
      else if (!d.dirs.length && !d.files.length) list.appendChild(el("div", "muted", "No folders or files here."));
    }).catch(function (e) {
      if (path) { browse(""); $("dlg-err").textContent = ""; return; }                          // a folder that is not allowed (or gone): start at the home folder instead
      $("dlg-err").textContent = e.message + (e.hint ? " - " + e.hint : "");
    });
  }
  function dirName(p) { var s = String(p).replace(/\\/g, "/"), i = s.lastIndexOf("/"); return i > 0 ? p.slice(0, i) : ""; }
  $("dlg-mkdir").addEventListener("click", function () {
    var name = $("dlg-newfolder").value.trim(); if (!name) { $("dlg-err").textContent = "Type a name for the new folder."; return; }
    var parent = (PICK && PICK.kind === "project") ? S.dlgProjectPath : (PICK && PICK.folder ? S.dlgFolderPath : S.dlgPath);
    api("/api/mkdir", null, { parent: parent, name: name }).then(function (r) { $("dlg-newfolder").value = ""; browse(r.path); })
      .catch(function (e) { $("dlg-err").textContent = e.message; });
  });
  function sep(p) { return p.indexOf("\\") >= 0 && p.indexOf("/") < 0 ? "\\" : "/"; }
  function openProjectDialog() { openDialog({ kind: "project", title: "Open a project", done: loadProjectFile }); }
  $("btn-open").addEventListener("click", function () { openDialog(); });
  $("btn-open2").addEventListener("click", function () { openDialog(); });
  $("btn-openproj").addEventListener("click", openProjectDialog);
  $("btn-openproj2").addEventListener("click", openProjectDialog);
  $("dlg-close").addEventListener("click", closeDialog);
  $("dlg-usefolder").addEventListener("click", function () {
    var cb = PICK && PICK.done, dir = PICK && PICK.kind === "project" ? S.dlgProjectPath : (PICK && PICK.folder ? S.dlgFolderPath : S.dlgPath), save = PICK && PICK.save, name = $("dlg-name").value.trim();
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
        var r = j.result || {}, changed = false;           // only redraw when something visible changed (a redraw replaces the clip elements)
        if (r.cache_id && !a.cacheId) a.cacheId = r.cache_id;
        if (r.playback && !a.src) {
          a.src = r.playback.kind === "original" ? url("/api/media", { path: a.path }) : url("/api/cache", { id: r.cache_id, name: r.playback.name });
          if (!$("video").getAttribute("data-src")) $("video").setAttribute("data-src", a.src);
          a.state = "ready"; busy(null); syncPlayback(); changed = true;
        }
        if (r.thumbs && !a.thumbs) { a.thumbs = r.thumbs; changed = true; }
        if (r.has_waveform && !a.peaks && !a.peaksLoading) { a.peaksLoading = true; api("/api/waveform", { id: r.cache_id }).then(function (p) { a.peaks = p; drawCanvases(); }); }
        if (j.state === "running") setTimeout(tick, 600);
        else if (j.state === "error" && !a.src) { a.state = "nopreview"; a.error = j.error.error; busy("Preview unavailable for " + a.name + ": " + j.error.error + " You can still cut and export."); changed = true; }
        if (changed) renderAll();
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
  function clearSel(except) {                      // one selection at a time: a clip, or one item of a layer
    if (except !== "clip") S.sel = -1; if (except !== "text") S.selText = -1; if (except !== "audio") S.selAudio = -1;
    if (except !== "overlay") S.selOv = -1; if (except !== "shape") S.selShape = -1; if (except !== "scene") S.selScene = -1; if (except !== "bg") S.selBg = -1;
  }
  function tab(name) { var b = document.querySelector('#tabs button[data-tab="' + name + '"]'); if (b) b.click(); }
  var HITS = [];                                   // what is under the mouse on the preview (filled while drawing, see pick.js)
  function snap() { return { clips: S.clips, sel: S.sel, canvas: S.canvas, bg: S.bg, texts: S.texts, audios: S.audios, overlays: S.overlays, shapes: S.shapes, scenes: S.scenes, bgs: S.bgs, tracks: S.tracks,
    selText: S.selText, selAudio: S.selAudio, selOv: S.selOv, selShape: S.selShape, selScene: S.selScene, selBg: S.selBg }; }
  function restore(p) {
    S.clips = p.clips; S.sel = p.sel; S.canvas = p.canvas || S.canvas; S.bg = p.bg || S.bg; S.dirty = true;
    S.texts = p.texts || []; S.audios = p.audios || []; S.selText = p.selText == null ? -1 : p.selText; S.selAudio = p.selAudio == null ? -1 : p.selAudio;
    S.overlays = p.overlays || []; S.selOv = p.selOv == null ? -1 : p.selOv;
    S.shapes = p.shapes || []; S.scenes = p.scenes || []; S.bgs = p.bgs || []; S.tracks = p.tracks || S.tracks; S.selBg = p.selBg == null ? -1 : p.selBg;
    S.selShape = p.selShape == null ? -1 : p.selShape; S.selScene = p.selScene == null ? -1 : p.selScene;
    syncCanvasControls(); afterEdit();
  }
  function commit(fn) { S.hist.push(snap()); fn(); S.dirty = true; renderAll(); }          // for changes that are not clip edits (texts, audio items)
  function ensureAsset(path, uploaded) {
    var existing = findAssetByPath(path); if (existing) return Promise.resolve(existing);
    return registerAsset(TL.uid("a"), path, null, uploaded);
  }
  function edit(fn) {
    S.hist.push(snap());
    var next = fn(S.clips);
    if (next) S.clips = next;
    S.dirty = true; if (S.sel >= S.clips.length) S.sel = S.clips.length - 1; afterEdit();
  }
  function afterEdit() { S.t = Math.min(S.t, TL.total(S.clips)); invalidatePreload(); syncPlayback(); renderAll(); }
  function undo() { var p = S.hist.undo(snap()); if (p) restore(p); }
  function redo() { var p = S.hist.redo(snap()); if (p) restore(p); }

  function addClipFromPath(path, uploaded) {
    busy("Reading " + baseName(path) + "…");
    return ensureAsset(path, uploaded).then(function (a) {
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
    if (window.VE && VE.layers && VE.layers.deleteSelected()) return;           // a selected text or audio item goes first
    if (S.sel < 0 || S.sel >= S.clips.length) { flash("Select a clip first (click it)."); return; }
    var i = S.sel; edit(function (c) { S.sel = Math.min(i, c.length - 2); return TL.removeIndex(c, i); });
  }
  function doDuplicate() {
    if (S.sel < 0) { flash("Select a clip first."); return; }
    var c = S.clips[S.sel], i = S.sel;
    edit(function (cl) { S.sel = i + 1; var d = { id: TL.uid("c"), asset: c.asset, "in": c["in"], out: c.out }; if (c.tf) d.tf = TL.cleanTf(c.tf); return TL.insertAt(cl, i + 1, d); });
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
    $("empty").hidden = S.clips.length > 0; $("stage-wrap").classList.toggle("empty-mode", S.clips.length === 0);
  }

  // ---------------------------------------------------------------- preview: two video elements, the next clip is preloaded
  var vids = [$("video"), $("video2")], ACT = 0, PB = { i: -1, playing: false };
  function act() { return vids[ACT]; }
  function idle() { return vids[1 - ACT]; }
  function show(v) { vids.forEach(function (x) { x.muted = x !== v; }); drawStage(); }
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
    drawPlayhead(); if (window.VE && VE.layers) VE.layers.stop();
  }
  function updatePlayIcon() { $("btn-play").innerHTML = PB.playing ? "&#10074;&#10074;" : "&#9654;"; }
  function togglePlay() {
    if (!S.clips.length) return;
    if (PB.playing) { PB.playing = false; vids.forEach(function (v) { v.pause(); }); updatePlayIcon(); if (window.VE && VE.layers) VE.layers.stop(); return; }
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
      if (!next) { PB.playing = false; vids.forEach(function (x) { x.pause(); }); S.t = L.total; updatePlayIcon(); drawPlayhead(); if (window.VE && VE.layers) VE.layers.stop(); return; }
      PB.i += 1;
      if (contiguous) { /* same file continues: nothing to switch */ }
      else if (idle().getAttribute("data-for") === next.id && idle().readyState >= 2) { v.pause(); ACT = 1 - ACT; show(act()); act().play(); }
      else attach(v, next.asset, next["in"], function () { act().play(); });
    }
    drawPlayhead(); drawStage(); if (window.VE && VE.layers) VE.layers.tick();
    requestAnimationFrame(tick);
  }
  vids.forEach(function (v) {
    v.addEventListener("loadedmetadata", layoutStage);
    ["seeked", "loadeddata", "timeupdate"].forEach(function (ev) { v.addEventListener(ev, function () { if (v === act() && !PB.playing) drawStage(); }); });
  });
  $("stage-canvas").addEventListener("click", function () { if (!stageDragged) togglePlay(); });
  $("btn-play").addEventListener("click", togglePlay);

  // ---------------------------------------------------------------- stage / guide
  function firstVideoDims() {
    for (var i = 0; i < S.clips.length; i++) { var a = assetFor(S.clips[i].asset), v = a && a.info && a.info.video; if (v) return [v.display_width || 1280, v.display_height || 720]; }
    return [1280, 720];
  }
  function canvasDims() { var f = firstVideoDims(); return TL.canvasSize(S.canvas.aspect, S.canvas.short, Math.floor(f[0] / 2) * 2, Math.floor(f[1] / 2) * 2); }
  function layoutStage() {
    var wrap = $("stage-wrap"), tr = $("transport").offsetHeight, d = canvasDims();
    var maxW = wrap.clientWidth - 40, maxH = wrap.clientHeight - tr - 40, ar = d[0] / d[1];
    var w = Math.min(maxW, maxH * ar), h = w / ar;
    var st = $("stage"); st.style.width = Math.max(100, Math.floor(w)) + "px"; st.style.height = Math.max(60, Math.floor(h)) + "px";
    drawStage();
  }

  // the preview is a canvas: background + the picture of the clip under the playhead, placed exactly like the export does it
  var blurBuf = document.createElement("canvas"), stageDragged = false;
  function drawStage() {
    var cv = $("stage-canvas"), st = $("stage"), d = canvasDims(), W = d[0], H = d[1];
    var cssW = st.clientWidth, cssH = st.clientHeight, dpr = window.devicePixelRatio || 1;
    if (!cssW || !cssH) return;
    if (cv.width !== Math.round(cssW * dpr) || cv.height !== Math.round(cssH * dpr)) { cv.width = Math.round(cssW * dpr); cv.height = Math.round(cssH * dpr); }
    var g = cv.getContext("2d"), k = cv.width / W;
    g.setTransform(1, 0, 0, 1, 0, 0); paintBackground(g, cv.width, cv.height);
    HITS.length = 0;
    var hit = currentHit(), a = hit && assetFor(hit.clip.asset), v = act();
    $("gizmo").hidden = true;
    var layers = function () { if (window.VE && VE.layers) VE.layers.drawStage(g, k, W, H); };
    if (!hit || !a || !a.hasVideo || !a.info || !a.info.video) { layers(); return; }
    var iw = a.info.video.display_width, ih = a.info.video.display_height, r = TL.fgRect(iw, ih, W, H, hit.clip.tf);
    updateGizmo(r, hit.index, cssW / W);
    HITS.push({ z: 0, rect: [r[0] * cssW / W, r[1] * cssW / W, r[2] * cssW / W, r[3] * cssW / W], gizmo: "gizmo", select: function () { clearSel("clip"); S.sel = hit.index; } });
    if (v.getAttribute("data-asset") !== a.id || !v.videoWidth || v.readyState < 2) { layers(); return; }
    var covers = r[0] <= 0 && r[1] <= 0 && r[0] + r[2] >= W && r[1] + r[3] >= H;
    if (effBg().mode === "blur" && !covers) {
      var bw = Math.max(8, Math.round(W / 8)), bh = Math.max(8, Math.round(H / 8)); blurBuf.width = bw; blurBuf.height = bh;
      var b = blurBuf.getContext("2d"), sc = Math.max(bw / v.videoWidth, bh / v.videoHeight), dw = v.videoWidth * sc, dh = v.videoHeight * sc;
      b.drawImage(v, (bw - dw) / 2, (bh - dh) / 2, dw, dh); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
      g.drawImage(blurBuf, 0, 0, bw, bh, 0, 0, cv.width, cv.height);
    }
    g.drawImage(v, r[0] * k, r[1] * k, r[2] * k, r[3] * k);
    layers();
  }
  function updateGizmo(r, index, kc) {                         // the frame around the picture that can be dragged
    var gz = $("gizmo");
    if (S.sel !== index || PB.playing) { gz.hidden = true; return; }
    gz.hidden = false; gz.style.left = (r[0] * kc) + "px"; gz.style.top = (r[1] * kc) + "px"; gz.style.width = (r[2] * kc) + "px"; gz.style.height = (r[3] * kc) + "px";
  }
  window.addEventListener("resize", function () { layoutStage(); drawAll(); });

  // ---------------------------------------------------------------- canvas, background and the position of the selected clip
  function targetIndex() { if (S.sel >= 0 && S.sel < S.clips.length) return S.sel; var h = currentHit(); return h ? h.index : -1; }
  function targetAsset() { var i = targetIndex(), c = i >= 0 ? S.clips[i] : null; return c ? assetFor(c.asset) : null; }
  function tfOf(i) { return TL.cleanTf(S.clips[i] && S.clips[i].tf); }
  function setTfLive(i, tf) {                                  // preview only; the history entry is added once per gesture
    var t = TL.cleanTf(tf);
    S.clips = S.clips.map(function (c, k) { if (k !== i) return c; var o = { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; o.tf = t; return o; });
    S.dirty = true; drawStage(); renderTfPanel(); renderInfo();
  }
  var gesture = null;
  function beginGesture() { if (!gesture) gesture = snap(); }
  function endGesture() { if (gesture) { S.hist.push(gesture); gesture = null; renderInfo(); } }
  function setTfCommit(i, tf) { beginGesture(); setTfLive(i, tf); endGesture(); }
  function renderTfPanel() {
    var i = targetIndex(), has = i >= 0, t = tfOf(i), asset = targetAsset();
    ["in-scale", "in-x", "in-y", "btn-tf-fit", "btn-tf-fill", "btn-tf-center", "btn-tf-reset", "btn-tf-all"].forEach(function (id) { $(id).disabled = !has || !(asset && asset.hasVideo); });
    $("in-scale").value = Math.round(t.s * 100); $("v-scale").textContent = Math.round(t.s * 100) + "%";
    $("in-x").value = Math.round(t.x * 100); $("v-x").textContent = Math.round(t.x * 100) + "%";
    $("in-y").value = Math.round(t.y * 100); $("v-y").textContent = Math.round(t.y * 100) + "%";
    var h = currentHit(), d = canvasDims();
    $("canvas-size").textContent = "Output: " + d[0] + " \u00D7 " + d[1] + " px";
    $("tf-hint").textContent = !has ? "Add a clip first." : !(asset && asset.hasVideo) ? "This clip has no picture." : (h && h.index !== i ? "Move the playhead into the selected clip to see it." : "Position and size apply to the selected clip only.");
  }
  // the canvas colour behind the pictures: black, one colour, a two-colour gradient or a picture (blur is drawn from the video)
  var bgImg = null, bgImgPath = "";
  function effBg() { return TL.activeBg(S.bgs, S.t) || S.bg; }              // the strip under the playhead, else the project background
  function bgTarget() { return S.selBg >= 0 && S.bgs[S.selBg] ? S.bgs[S.selBg] : S.bg; }   // what the Background controls edit
  function paintBackground(g, w, h) {
    var bg = effBg(), m = bg.mode;
    if (m === "gradient") { var gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, bg.color); gr.addColorStop(1, bg.color2 || "#1b1464"); g.fillStyle = gr; g.fillRect(0, 0, w, h); return; }
    if (m === "image" && bg.image) {
      if (bgImgPath !== bg.image) { bgImgPath = bg.image; bgImg = new Image(); bgImg.onload = function () { drawStage(); }; bgImg.src = url("/api/image", { path: bg.image }); }
      g.fillStyle = "#000"; g.fillRect(0, 0, w, h);
      if (bgImg && bgImg.complete && bgImg.naturalWidth) { var sc = Math.max(w / bgImg.naturalWidth, h / bgImg.naturalHeight), dw = bgImg.naturalWidth * sc, dh = bgImg.naturalHeight * sc; g.drawImage(bgImg, (w - dw) / 2, (h - dh) / 2, dw, dh); }
      return;
    }
    g.fillStyle = m === "color" ? bg.color : "#000"; g.fillRect(0, 0, w, h);
  }
  function bgSegForExport(s) { var o = bgLook(s); o.start = s.start; o.dur = s.dur; o.track = s.track || 0; return o; }
  function bgLook(b) { return b.mode === "gradient" ? { mode: "gradient", color: b.color, color2: b.color2 } : b.mode === "image" ? (b.image ? { mode: "image", color: b.color, image: b.image } : { mode: "black", color: b.color }) : { mode: b.mode, color: b.color }; }
  function bgForExport() { var b = S.bg; return b.mode === "gradient" ? { mode: "gradient", color: b.color, color2: b.color2 } : b.mode === "image" ? (b.image ? { mode: "image", color: b.color, image: b.image } : { mode: "black", color: b.color }) : { mode: b.mode, color: b.color }; }
  function syncCanvasControls() {
    $("in-aspect").value = S.canvas.aspect; $("in-short").value = String(S.canvas.short); var bt = bgTarget(); $("in-bg").value = bt.mode; $("in-bgcolor").value = bt.color;
    $("in-bgcolor").hidden = !(bt.mode === "color" || bt.mode === "gradient"); $("in-bgcolor2").hidden = bt.mode !== "gradient"; $("in-bgcolor2").value = bt.color2 || "#1b1464";
    $("bg-image-row").hidden = bt.mode !== "image"; $("bg-image-name").textContent = bt.image ? baseName(bt.image) : "No picture chosen";
    $("bg-target").textContent = S.selBg >= 0 && S.bgs[S.selBg] ? "Editing the selected background strip (" + fmt(S.bgs[S.selBg].start) + " \u2192 " + fmt(S.bgs[S.selBg].start + S.bgs[S.selBg].dur) + ")" : "Editing the project background (valid wherever no strip lies on top)";
    $("btn-bg-strip-del").hidden = !(S.selBg >= 0 && S.bgs[S.selBg]); $("btn-bg-strip-all").hidden = !(S.selBg >= 0 && S.bgs[S.selBg]);
    $("in-short").disabled = S.canvas.aspect === "auto";
  }
  function changeCanvas(patchCanvas, patchBg) {
    S.hist.push(snap());
    if (patchCanvas) S.canvas = Object.assign({}, S.canvas, patchCanvas);
    if (patchBg) { if (S.selBg >= 0 && S.bgs[S.selBg]) S.bgs = S.bgs.map(function (x, k) { return k === S.selBg ? TL.cleanBgSeg(Object.assign({}, x, patchBg)) : x; }); else S.bg = Object.assign({}, S.bg, patchBg); }
    S.dirty = true; syncCanvasControls(); layoutStage(); renderAll();
  }
  $("in-aspect").addEventListener("change", function () { changeCanvas({ aspect: this.value }); });
  $("in-short").addEventListener("change", function () { changeCanvas({ short: +this.value }); });
  $("in-bg").addEventListener("change", function () { changeCanvas(null, { mode: this.value }); if (this.value === "image" && !bgTarget().image) $("btn-bg-image").click(); });
  $("in-bgcolor").addEventListener("change", function () { changeCanvas(null, { color: this.value }); });
  $("in-bgcolor2").addEventListener("change", function () { changeCanvas(null, { color2: this.value }); });
  $("btn-bg-image").addEventListener("click", function () {
    openDialog({ kind: "picture", title: "Choose a background picture", done: function (p) { changeCanvas(null, { mode: "image", image: p }); } });
  });
  [["in-scale", function (t, v) { t.s = v / 100; }], ["in-x", function (t, v) { t.x = v / 100; }], ["in-y", function (t, v) { t.y = v / 100; }]].forEach(function (pair) {
    $(pair[0]).addEventListener("input", function () { var i = targetIndex(); if (i < 0) return; beginGesture(); var t = tfOf(i); pair[1](t, +this.value); setTfLive(i, t); });
    $(pair[0]).addEventListener("change", endGesture);
  });
  function tfPreset(kind) {
    var i = targetIndex(), a = targetAsset(); if (i < 0 || !a || !a.hasVideo) return;
    var d = canvasDims(), v = a.info.video, t = tfOf(i);
    if (kind === "fit") t.s = 1; else if (kind === "fill") t.s = TL.fillScale(v.display_width, v.display_height, d[0], d[1]); else if (kind === "center") { t.x = 0; t.y = 0; } else { t = { s: 1, x: 0, y: 0 }; }
    setTfCommit(i, t);
  }
  $("btn-tf-fit").addEventListener("click", function () { tfPreset("fit"); });
  $("btn-tf-fill").addEventListener("click", function () { tfPreset("fill"); });
  $("btn-tf-center").addEventListener("click", function () { tfPreset("center"); });
  $("btn-tf-reset").addEventListener("click", function () { tfPreset("reset"); });
  $("btn-tf-all").addEventListener("click", function () {
    var i = targetIndex(); if (i < 0) return; var t = tfOf(i);
    edit(function (c) { return c.map(function (x) { var o = { id: x.id, asset: x.asset, "in": x["in"], out: x.out, tf: { s: t.s, x: t.x, y: t.y } }; return o; }); });
  });

  // drag the picture on the preview (move), drag a corner (zoom), mouse wheel (zoom)
  (function () {
    var drag = null, magnet = 0.012;
    function pt(e) { var r = $("stage").getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height }; }
    $("gizmo").addEventListener("mousedown", function (e) {
      var i = targetIndex(); if (i < 0 || e.button !== 0) return;
      var corner = e.target.getAttribute && e.target.getAttribute("data-corner"), p = pt(e), t = tfOf(i), g = $("gizmo");
      var cx = g.offsetLeft + g.offsetWidth / 2, cy = g.offsetTop + g.offsetHeight / 2;
      drag = { i: i, corner: corner, x0: p.x, y0: p.y, t: t, w: p.w, h: p.h, d0: Math.max(1, Math.hypot(p.x - cx, p.y - cy)), cx: cx, cy: cy };
      stageDragged = false; beginGesture(); e.preventDefault(); e.stopPropagation();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return;
      var p = pt(e), t = { s: drag.t.s, x: drag.t.x, y: drag.t.y };
      if (drag.corner) t.s = drag.t.s * Math.hypot(p.x - drag.cx, p.y - drag.cy) / drag.d0;
      else {
        t.x = drag.t.x + (p.x - drag.x0) / drag.w; t.y = drag.t.y + (p.y - drag.y0) / drag.h;
        if (Math.abs(t.x) < magnet) t.x = 0; if (Math.abs(t.y) < magnet) t.y = 0;          // snap to the centre lines
      }
      if (Math.abs(p.x - drag.x0) + Math.abs(p.y - drag.y0) > 3) stageDragged = true;
      setTfLive(drag.i, t);
    });
    window.addEventListener("mouseup", function () { if (!drag) return; drag = null; endGesture(); setTimeout(function () { stageDragged = false; }, 0); });
    $("stage").addEventListener("wheel", function (e) {
      var i = targetIndex(), a = targetAsset(); if (i < 0 || !a || !a.hasVideo) return;
      e.preventDefault(); var t = tfOf(i); t.s = t.s * Math.exp(-e.deltaY * 0.0015); setTfCommit(i, t);
    }, { passive: false });
  })();

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
    [["ruler", 26], ["wave", 72]].forEach(function (p) {
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
    var w = $("wave").getContext("2d"), H = 72, mid = H / 2, amp = mid - 5, col = cssColor("--accent", "#8b6cf0");
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
    if (window.VE && VE.layers) VE.layers.drawCanvases(vw, x0, dpr);
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
  function drawAll() { sizeTrack(); drawCanvases(); drawClips(); drawPlayhead(); if (window.VE && VE.layers) VE.layers.drawLanes(); }
  function renderAll() { renderMarks(); renderInfo(); drawAll(); renderTfPanel(); drawStage(); if (window.VE && VE.layers) VE.layers.render(); }

  // mouse on the timeline: click/drag empty space = scrub, Shift+drag = mark a range, drag a clip = reorder, drag an edge = trim
  (function () {
    var drag = null;
    function tAt(e) { var r = $("track").getBoundingClientRect(); return clamp((e.clientX - r.left) / S.zoom, 0, total()); }
    $("track").addEventListener("mousedown", function (e) {
      if (e.button !== 0 || !S.clips.length) return;
      var clipEl = e.target.closest ? e.target.closest(".clip") : null;
      if (clipEl && !e.shiftKey) {
        var i = +clipEl.getAttribute("data-i"), edge = e.target.getAttribute && e.target.getAttribute("data-edge");
        clearSel("clip"); S.sel = i; seek(tAt(e));
        drag = { kind: edge ? "trim" : "move", i: i, edge: edge, x0: e.clientX, base: S.clips, moved: false };
        renderAll(); e.preventDefault(); return;
      }
      drag = { kind: e.shiftKey ? "mark" : "scrub", t0: tAt(e) };
      if (drag.kind === "scrub") { clearSel("none"); seek(drag.t0); renderAll(); }
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
    var used = {}; S.clips.forEach(function (c) { used[c.asset] = true; }); S.audios.forEach(function (a) { used[a.asset] = true; }); S.overlays.forEach(function (o) { used[o.asset] = true; });
    var assets = {}; Object.keys(used).forEach(function (id) { var a = S.assets[id]; if (a) assets[id] = { path: a.path, name: a.name }; });
    return { version: 1, name: S.projectName || "", assets: assets, canvas: S.canvas, bg: S.bg, texts: S.texts.map(TL.cleanText),
      audios: S.audios.map(TL.cleanAudio), overlays: S.overlays.map(TL.cleanOverlay),
      shapes: S.shapes.map(TL.cleanShape), scenes: S.scenes.map(TL.cleanScene), bgs: S.bgs.map(TL.cleanBgSeg), tracks: window.VE && VE.tracks ? VE.tracks.normalized() : S.tracks,
      clips: S.clips.map(function (c) { var o = { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; if (c.tf) o.tf = TL.cleanTf(c.tf); return o; }) };
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
      S.assets = {}; S.clips = []; S.sel = -1; S.texts = []; S.audios = []; S.overlays = []; S.shapes = []; S.scenes = []; S.bgs = []; S.tracks = TL.cleanTracks(null); clearSel("none"); S.t = 0; S.mark = { a: null, b: null }; S.hist = TL.createHistory(100);
      var ids = Object.keys(p.assets);
      return Promise.all(ids.map(function (id) { return registerAsset(id, p.assets[id].path, p.assets[id].name).catch(function () { return null; }); })).then(function () {
        S.clips = p.clips.map(function (c) { var o = { id: c.id, asset: c.asset, "in": c["in"], out: c.out }; if (c.tf) o.tf = c.tf; return o; });
        S.canvas = p.canvas || { aspect: "auto", short: 1080 }; S.bg = Object.assign({ mode: "blur", color: "#000000", color2: "#1b1464", image: "" }, p.bg || {}); syncCanvasControls();
        S.texts = (p.texts || []).map(TL.cleanText); S.audios = (p.audios || []).map(TL.cleanAudio); S.overlays = (p.overlays || []).map(TL.cleanOverlay); S.shapes = (p.shapes || []).map(TL.cleanShape); S.scenes = (p.scenes || []).map(TL.cleanScene); S.bgs = (p.bgs || []).map(TL.cleanBgSeg);
        S.tracks = TL.cleanTracks(p.tracks); S.selText = -1; S.selAudio = -1;
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
  function chooseOutDir() { openDialog({ kind: "media", folder: true, title: "Choose the folder for the exported video", done: function (p) { $("in-outdir").value = p; } }); }
  $("btn-outdir").addEventListener("click", chooseOutDir);
  $("in-outdir").addEventListener("click", function () { if (!this.value.trim()) chooseOutDir(); });
  $("btn-export").addEventListener("click", function () {
    if (!S.clips.length) { openDialog(); return; }
    var body = {
      clips: TL.forExport(S.clips, S.assets), canvas: S.canvas, bg: bgForExport(), bgs: S.bgs.map(bgSegForExport), texts: S.texts.map(TL.cleanText), shapes: S.shapes.map(TL.cleanShape),
      audios: S.audios.filter(function (a) { return S.assets[a.asset] && !S.assets[a.asset].error; }).map(function (a) { return { path: S.assets[a.asset].path, "in": a["in"], out: a.out, start: a.start, vol: a.vol, fi: a.fi, fo: a.fo, duck: a.duck, track: a.track || 0 }; }),
      overlays: S.overlays.filter(function (o) { return S.assets[o.asset] && !S.assets[o.asset].error; }).map(function (o) { return { path: S.assets[o.asset].path, "in": o["in"], out: o.out, start: o.start, tf: o.tf, op: o.op, sound: o.sound, vol: o.vol, track: o.track || 0 }; }), speed: +$("in-speed").value, reframe: "none",
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
        b.appendChild(el("b", "", t.name.replace(/^lk_/, "")));
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
  window.VE = { S: S, TL: TL, $: $, el: el, fmt: fmt, clamp: clamp, api: api, url: url, assetFor: assetFor, ensureAsset: ensureAsset, snap: snap, commit: commit,
    renderAll: renderAll, drawStage: drawStage, drawCanvases: drawCanvases, seek: seek, flash: flash, openDialog: openDialog, cssColor: cssColor, baseName: baseName,
    canvasDims: canvasDims, playing: function () { return PB.playing; }, gestureBegin: beginGesture, gestureEnd: endGesture, layers: null, tab: tab, clearSel: clearSel, hits: HITS,
    bgTarget: bgTarget, syncCanvasControls: syncCanvasControls, ops: { split: doSplit, clone: doDuplicate, remove: doDelete, undo: undo, redo: redo, edit: edit } };
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
  show(vids[0]); syncCanvasControls(); layoutStage(); renderAll(); init();
  if (typeof ResizeObserver === "function") {          // the frame may be laid out after the first paint (Hermes Desktop): follow every size change
    var ro = new ResizeObserver(function () { layoutStage(); drawAll(); });
    ro.observe($("stage-wrap")); ro.observe($("tl-scroll"));
  }
})();
