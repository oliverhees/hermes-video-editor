"use strict";
/* Video Editor UI: plain JS, no dependencies. Talks to the local server it was loaded from. */
(function () {
  var Q = new URLSearchParams(location.search);
  var TOKEN = Q.get("t") || "";
  var $ = function (id) { return document.getElementById(id); };
  var S = {
    path: null, info: null, dur: 0, cuts: [], mark: { a: null, b: null }, sel: -1, zoom: 80,
    peaks: null, thumbs: null, cacheId: null, config: null, anchor: "center", dlgPath: "", prepJob: null,
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
  function merged(cuts) {
    var c = cuts.map(function (x) { return [x[0], x[1]]; }).sort(function (a, b) { return a[0] - b[0]; }), out = [];
    c.forEach(function (x) { if (out.length && x[0] <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], x[1]); else out.push(x); });
    return out;
  }
  function busy(msg) { var o = $("overlay"); o.hidden = !msg; o.textContent = msg || ""; $("empty").hidden = !!S.path; }

  // ---------------------------------------------------------------- theme (sent by the Hermes Desktop page)
  var HEX = /^#[0-9a-f]{6}$/i;
  function applyTheme(t) {
    if (!t) return;
    var root = document.documentElement;
    if (t.theme === "light" || t.theme === "dark") root.setAttribute("data-theme", t.theme);
    if (HEX.test(t.bg || "") && HEX.test(t.fg || "")) { root.style.setProperty("--bg", t.bg); root.style.setProperty("--text", t.fg); root.setAttribute("data-derive", "1"); }
    if (HEX.test(t.accent || "")) root.style.setProperty("--accent", t.accent);
    if (S.dur) drawAll();
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

  // ---------------------------------------------------------------- file dialog
  var PICK = null;   // {kind, folder, done} while the dialog picks a file/folder for a tool field instead of opening a video
  function openDialog(pick) {
    PICK = pick && pick.kind ? pick : null;
    $("modal").hidden = false; $("dlg-usefolder").hidden = !(PICK && PICK.folder);
    browse(S.dlgPath || store("ve.dir") || "");
    var show = !PICK; $("dlg-recent").hidden = !show; if (!show) $("dlg-recent-title").hidden = true;
    if (show) fillRecent($("dlg-recent"), $("dlg-recent-title"), closeDialog);
  }
  function fillRecent(list, title, after) {
    api("/api/recent").then(function (r) {
      list.textContent = ""; title.hidden = !r.files.length;
      r.files.slice(0, 6).forEach(function (f) {
        var it = el("div", "item"); it.appendChild(el("span", "grow", "\uD83C\uDFAC " + f.name)); it.title = f.path;
        it.addEventListener("click", function () { if (after) after(); loadFile(f.path); }); list.appendChild(it);
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
        var it = el("div", "item"); it.appendChild(el("span", "grow", "🎬 " + x.name));
        it.appendChild(el("span", "muted", (x.size / 1048576).toFixed(1) + " MB"));
        it.addEventListener("click", function () {
          var full = d.path + sep(d.path) + x.name; closeDialog();
          if (PICK) { if (PICK.done) PICK.done(full); } else loadFile(full);
        }); list.appendChild(it);
      });
      if (!d.dirs.length && !d.files.length) list.appendChild(el("div", "muted", "No folders or videos here."));
    }).catch(function (e) { $("dlg-err").textContent = e.message + (e.hint ? " - " + e.hint : ""); });
  }
  function sep(p) { return p.indexOf("\\") >= 0 && p.indexOf("/") < 0 ? "\\" : "/"; }
  $("btn-open").addEventListener("click", function () { openDialog(); });
  $("btn-open2").addEventListener("click", function () { openDialog(); });
  $("dlg-usefolder").addEventListener("click", function () { var d = S.dlgPath, cb = PICK && PICK.done; closeDialog(); if (cb) cb(d); });
  $("dlg-close").addEventListener("click", closeDialog);
  $("dlg-path").addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var v = this.value.trim();
    if (/\.[A-Za-z0-9]{2,4}$/.test(v)) { var cb = PICK && PICK.done; closeDialog(); if (PICK) { if (cb) cb(v); } else loadFile(v); } else browse(v);
  });

  // ---------------------------------------------------------------- loading a file
  function resetState() {
    S.fitted = false; S.cuts = []; S.mark = { a: null, b: null }; S.sel = -1; S.peaks = null; S.thumbs = null; S.cacheId = null;
    $("thumbs").textContent = ""; $("result").hidden = true; $("job").hidden = true;
  }
  function loadFile(path, uploaded) {
    resetState(); S.path = path; $("empty").hidden = true;
    if (uploaded && S.config && !$("in-outdir").value) $("in-outdir").value = S.config.videos_dir;
    $("file-chip").textContent = path; $("file-chip").title = path;
    busy("Reading file…");
    api("/api/probe", { path: path }).then(function (info) {
      S.info = info; S.dur = info.duration_s || 0;
      busy("Preparing preview…");
      var h264 = !!document.createElement("video").canPlayType('video/mp4; codecs="avc1.42E01E"');
      return api("/api/prepare", null, { path: path, h264: h264 });
    }).then(function (r) { pollPrepare(r.job); renderAll(); updateGuide(); })
      .catch(function (e) { busy("Could not open: " + e.message + (e.hint ? " (" + e.hint + ")" : "")); });
  }
  function pollPrepare(id) {
    S.prepJob = id;
    (function tick() {
      if (S.prepJob !== id) return;
      api("/api/job", { id: id }).then(function (j) {
        var r = j.result || {};
        if (r.cache_id && !S.cacheId) S.cacheId = r.cache_id;
        if (r.duration_s && !S.dur) { S.dur = r.duration_s; }
        if (S.dur && !S.fitted) { S.fitted = true; fit(); }
        if (r.playback && !$("video").getAttribute("data-src")) {
          var src = r.playback.kind === "original" ? url("/api/media", { path: S.path }) : url("/api/cache", { id: r.cache_id, name: r.playback.name });
          $("video").setAttribute("data-src", src); $("video").src = src; busy(null);
        }
        if (r.thumbs && !S.thumbs) { S.thumbs = r.thumbs; drawThumbs(); }
        if (r.has_waveform && !S.peaks) {
          api("/api/waveform", { id: r.cache_id }).then(function (p) { S.peaks = p; drawCanvases(); });
        }
        if (j.state === "running") setTimeout(tick, 600);
        else if (j.state === "error") { if (!$("video").getAttribute("data-src")) busy("Preview unavailable: " + j.error.error + " You can still mark cuts and export."); }
        renderAll();
      }).catch(function () { setTimeout(tick, 1500); });
    })();
  }

  // ---------------------------------------------------------------- stage / guide
  function layoutStage() {
    var wrap = $("stage-wrap"), tr = $("transport").offsetHeight;
    var v = $("video"), ar = (v.videoWidth && v.videoHeight) ? v.videoWidth / v.videoHeight :
      (S.info && S.info.video ? S.info.video.display_width / S.info.video.display_height : 16 / 9);
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
    if (w < W - 1) x = ({ left: 0, right: W - w })[S.anchor] != null ? ({ left: 0, right: W - w })[S.anchor] : x;
    if (h < H - 1) y = ({ top: 0, bottom: H - h })[S.anchor] != null ? ({ top: 0, bottom: H - h })[S.anchor] : y;
    g.hidden = false; g.style.left = x + "px"; g.style.top = y + "px"; g.style.width = w + "px"; g.style.height = h + "px";
  }
  $("video").addEventListener("loadedmetadata", function () { if (!S.dur && isFinite(this.duration)) S.dur = this.duration; layoutStage(); renderAll(); });
  window.addEventListener("resize", function () { layoutStage(); drawAll(); });

  // ---------------------------------------------------------------- transport
  function togglePlay() { var v = $("video"); if (!v.src) return; if (v.paused) v.play(); else v.pause(); }
  $("btn-play").addEventListener("click", togglePlay);
  $("video").addEventListener("play", function () { $("btn-play").innerHTML = "&#10074;&#10074;"; loop(); });
  $("video").addEventListener("pause", function () { $("btn-play").innerHTML = "&#9654;"; });
  $("video").addEventListener("click", togglePlay);
  function loop() {
    var v = $("video");
    if ($("in-skip").checked) {
      var cuts = merged(S.cuts);
      for (var i = 0; i < cuts.length; i++) if (v.currentTime >= cuts[i][0] && v.currentTime < cuts[i][1]) { v.currentTime = cuts[i][1]; break; }
    }
    drawPlayhead();
    if (!v.paused && !v.ended) requestAnimationFrame(loop);
  }
  $("video").addEventListener("timeupdate", drawPlayhead);
  $("video").addEventListener("seeked", drawPlayhead);
  function seek(t) { var v = $("video"); if (v.src) v.currentTime = clamp(t, 0, S.dur || v.duration || 0); drawPlayhead(); }
  function now() { return $("video").currentTime || 0; }

  // ---------------------------------------------------------------- marks & cuts
  function setIn() { S.mark.a = now(); if (S.mark.b != null && S.mark.b <= S.mark.a) S.mark.b = null; renderAll(); }
  function setOut() { S.mark.b = now(); if (S.mark.a != null && S.mark.a >= S.mark.b) S.mark.a = null; renderAll(); }
  function addCut() {
    var a = S.mark.a, b = S.mark.b;
    if (a == null || b == null || b - a < 0.05) { flash("Mark a range first (I and O)."); return; }
    S.cuts.push([a, b]); S.mark = { a: null, b: null }; S.sel = -1; renderAll();
  }
  function flash(msg) { $("marks").textContent = msg; setTimeout(renderMarks, 1800); }
  $("btn-in").addEventListener("click", setIn);
  $("btn-out").addEventListener("click", setOut);
  $("btn-cut").addEventListener("click", addCut);
  $("btn-silence").addEventListener("click", function () {
    if (!S.path) return;
    var btn = this; btn.disabled = true; btn.textContent = "Searching…";
    api("/api/silence", null, { path: S.path, noise_db: +$("in-noise").value, min_silence_s: +$("in-minsil").value }).then(function (r) {
      var pad = 0.1, added = 0;
      r.silences.forEach(function (s) { if (s.end_s - s.start_s > 2 * pad + 0.02) { S.cuts.push([s.start_s + pad, s.end_s - pad]); added++; } });
      flash(added ? added + " silences added as cuts." : "No silence found at this level.");
      btn.disabled = false; btn.textContent = "Find silences"; renderAll();
    }).catch(function (e) { btn.disabled = false; btn.textContent = "Find silences"; flash(e.message); });
  });

  function renderMarks() {
    var m = S.mark;
    $("marks").textContent = m.a == null && m.b == null ? "No range marked. Press I and O at the playhead, or drag on the timeline with Shift."
      : "Marked: " + (m.a == null ? "?" : fmt(m.a)) + " → " + (m.b == null ? "?" : fmt(m.b)) + (m.a != null && m.b != null ? "  (" + (m.b - m.a).toFixed(1) + " s)" : "");
  }
  function renderCuts() {
    var list = $("cuts-list"); list.textContent = "";
    $("cut-count").textContent = S.cuts.length;
    S.cuts.forEach(function (c, i) {
      var it = el("div", "item" + (i === S.sel ? " sel" : ""));
      it.appendChild(el("span", "grow", fmt(c[0]) + " → " + fmt(c[1]) + "  (" + (c[1] - c[0]).toFixed(1) + " s)"));
      var edit = el("button", "x", "✎"); edit.title = "Move into the marked range to adjust";
      edit.addEventListener("click", function (e) { e.stopPropagation(); S.mark = { a: c[0], b: c[1] }; S.cuts.splice(i, 1); S.sel = -1; renderAll(); });
      var rm = el("button", "x", "✕"); rm.title = "Remove this cut";
      rm.addEventListener("click", function (e) { e.stopPropagation(); S.cuts.splice(i, 1); S.sel = -1; renderAll(); });
      it.appendChild(edit); it.appendChild(rm);
      it.addEventListener("click", function () { S.sel = i; seek(c[0]); renderAll(); });
      list.appendChild(it);
    });
    var removed = merged(S.cuts).reduce(function (s, c) { return s + (Math.min(c[1], S.dur || c[1]) - c[0]); }, 0);
    var speed = +$("in-speed").value || 1;
    $("summary").textContent = S.dur ? "Keeps " + fmt(Math.max(0, S.dur - removed) / speed) + " of " + fmt(S.dur) + (speed !== 1 ? " (speed " + speed + "×)" : "") : "";
  }
  $("in-speed").addEventListener("change", renderCuts);

  // ---------------------------------------------------------------- timeline drawing
  function trackWidth() { return Math.max($("tl-scroll").clientWidth, Math.ceil((S.dur || 1) * S.zoom)); }
  function fit() { S.zoom = Math.max(4, ($("tl-scroll").clientWidth - 2) / (S.dur || 1)); renderAll(); $("tl-scroll").scrollLeft = 0; }
  function zoomBy(f) {
    var sc = $("tl-scroll"), centre = (sc.scrollLeft + sc.clientWidth / 2) / S.zoom;
    S.zoom = clamp(S.zoom * f, 4, 2000); renderAll(); sc.scrollLeft = centre * S.zoom - sc.clientWidth / 2;
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
    // ruler
    var g = $("ruler").getContext("2d"), step = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find(function (s) { return s * S.zoom >= 70; }) || 600;
    g.fillStyle = cssColor("--muted", "#8a94a8"); g.font = "11px ui-monospace, monospace"; g.strokeStyle = cssColor("--line", "#3a4560");
    for (var t = Math.floor(x0 / S.zoom / step) * step; t * S.zoom - x0 < vw + 80; t += step) {
      var x = Math.round(t * S.zoom - x0) + 0.5; g.beginPath(); g.moveTo(x, 14); g.lineTo(x, 26); g.stroke();
      g.fillText(fmt(t, step < 1), x + 4, 12);
    }
    // waveform: mirrored, smoothed envelope with a vertical gradient
    var w = $("wave").getContext("2d"), H = 110, mid = H / 2, amp = mid - 6;
    if (S.peaks && S.peaks.length && S.dur) {
      var per = S.peaks.length / S.dur, top = [], px;                  // peaks per second
      for (px = 0; px < vw; px++) {
        var ta = (x0 + px) / S.zoom, tb = (x0 + px + 1) / S.zoom;
        var ia = Math.floor(ta * per), ib = Math.max(ia + 1, Math.ceil(tb * per)), m = 0, sum = 0, n = 0;
        for (var i = ia; i < ib && i < S.peaks.length; i++) { if (S.peaks[i] > m) m = S.peaks[i]; sum += S.peaks[i]; n++; }
        top.push(n ? Math.pow(0.65 * m + 0.35 * (sum / n), 0.85) : 0);   // mix of peak and average = readable at every zoom
      }
      var sm = top.map(function (v, k) { var a1 = top[Math.max(0, k - 1)], a2 = top[Math.min(top.length - 1, k + 1)]; return (a1 + 2 * v + a2) / 4; });
      var col = cssColor("--teal", "#4ecdc4");
      w.globalAlpha = 0.28; w.fillStyle = col; w.fillRect(0, mid - 0.5, vw, 1); w.globalAlpha = 1;
      w.beginPath(); w.moveTo(0, mid);
      for (px = 0; px < vw; px++) w.lineTo(px, mid - Math.max(1, sm[px] * amp));
      w.lineTo(vw, mid);
      for (px = vw - 1; px >= 0; px--) w.lineTo(px, mid + Math.max(1, sm[px] * amp));
      w.closePath();
      w.globalAlpha = 0.9; w.fillStyle = col; w.fill();
      w.globalAlpha = 1; w.lineWidth = 1; w.strokeStyle = col; w.stroke();
    } else if (S.info && !S.info.has_audio) {
      w.fillStyle = cssColor("--muted", "#8a94a8"); w.font = "12px system-ui"; w.fillText("No audio track", 12, mid);
    } else if (S.path) {
      w.fillStyle = cssColor("--muted", "#8a94a8"); w.font = "12px system-ui"; w.fillText("Reading audio\u2026", 12, mid);
    }
  }
  function drawThumbs() {
    var box = $("thumbs"); box.textContent = "";
    if (!S.thumbs || !S.dur) return;
    var n = S.thumbs.count, src = url("/api/cache", { id: S.cacheId, name: S.thumbs.name }), span = S.dur / n;
    for (var i = 0; i < n; i++) {
      var d = document.createElement("i");
      d.style.width = (span * S.zoom) + "px";
      d.style.backgroundImage = "url('" + src + "')";
      d.style.backgroundSize = (n * 100) + "% 100%";
      d.style.backgroundPosition = (n > 1 ? i / (n - 1) * 100 : 0) + "% 0";
      box.appendChild(d);
    }
  }
  function drawRegions() {
    var box = $("regions"); box.textContent = "";
    S.cuts.forEach(function (c, i) {
      var d = el("div", "region" + (i === S.sel ? " sel" : ""));
      d.style.left = (c[0] * S.zoom) + "px"; d.style.width = Math.max(2, (c[1] - c[0]) * S.zoom) + "px"; box.appendChild(d);
    });
    var mr = $("mark-range"), a = S.mark.a, b = S.mark.b;
    if (a != null || b != null) {
      var s = a != null ? a : b, e = b != null ? b : a; mr.hidden = false;
      mr.style.left = (s * S.zoom) + "px"; mr.style.width = Math.max(2, (e - s) * S.zoom) + "px";
    } else mr.hidden = true;
  }
  function drawPlayhead() {
    var t = now(); $("playhead").style.left = (t * S.zoom) + "px";
    $("time").textContent = fmt(t) + " / " + fmt(S.dur);
    var sc = $("tl-scroll"), x = t * S.zoom;
    if (!$("video").paused && (x < sc.scrollLeft || x > sc.scrollLeft + sc.clientWidth - 40)) sc.scrollLeft = x - 60;
  }
  function drawAll() { sizeTrack(); drawCanvases(); drawThumbs(); drawRegions(); drawPlayhead(); }
  function renderAll() { renderMarks(); renderCuts(); drawAll(); }

  // timeline mouse: click/drag = scrub, shift-drag = mark range
  (function () {
    var drag = null;
    function tAt(e) { var r = $("track").getBoundingClientRect(); return clamp((e.clientX - r.left) / S.zoom, 0, S.dur || 0); }
    $("track").addEventListener("mousedown", function (e) {
      if (e.button !== 0 || !S.dur) return;
      drag = { shift: e.shiftKey, t0: tAt(e) };
      if (!drag.shift) seek(drag.t0);
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) {
      if (!drag) return;
      var t = tAt(e);
      if (drag.shift) { S.mark = { a: Math.min(drag.t0, t), b: Math.max(drag.t0, t) }; renderAll(); } else seek(t);
    });
    window.addEventListener("mouseup", function () { drag = null; });
  })();

  // ---------------------------------------------------------------- keyboard
  window.addEventListener("keydown", function (e) {
    if (/INPUT|SELECT|TEXTAREA/.test((e.target.tagName || "")) && e.target.type !== "range" && e.target.type !== "checkbox") return;
    if (!$("modal").hidden) { if (e.key === "Escape") closeDialog(); return; }
    var k = e.key.toLowerCase(), fps = (S.info && S.info.video && S.info.video.fps) || 25;
    if (k === " ") { e.preventDefault(); togglePlay(); }
    else if (k === "i") setIn();
    else if (k === "o") setOut();
    else if (k === "x") addCut();
    else if (k === "arrowleft") { e.preventDefault(); seek(now() - (e.shiftKey ? 1 : 1 / fps)); }
    else if (k === "arrowright") { e.preventDefault(); seek(now() + (e.shiftKey ? 1 : 1 / fps)); }
    else if (k === "delete" || k === "backspace") { if (S.sel >= 0) { S.cuts.splice(S.sel, 1); S.sel = -1; renderAll(); } }
    else if (k === "+" || k === "=") zoomBy(1.5);
    else if (k === "-") zoomBy(1 / 1.5);
  });

  // ---------------------------------------------------------------- export
  $("btn-export").addEventListener("click", function () {
    if (!S.path) { openDialog(); return; }
    var body = {
      path: S.path, cuts: merged(S.cuts), speed: +$("in-speed").value, reframe: $("in-reframe").value, anchor: S.anchor,
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
    if (r.platform_check) {
      var pc = r.platform_check; box.appendChild(el("div", pc.passed ? "ok" : "bad", pc.label + ": " + (pc.passed ? "all checks passed" : "needs fixes")));
      var ul = el("ul");
      pc.checks.forEach(function (c) { ul.appendChild(el("li", c.status, (c.status === "pass" ? "✓ " : c.status === "fail" ? "✗ " : "! ") + c.check + ": " + c.value + (c.status !== "pass" && c.fix ? "  - " + c.fix : ""))); });
      box.appendChild(ul);
    }
  }

  // ---------------------------------------------------------------- drag & drop (browsers hide real paths, so the file is copied)
  (function () {
    var depth = 0;
    function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0; }
    window.addEventListener("dragenter", function (e) { if (hasFiles(e)) { depth++; document.body.classList.add("drop-on"); e.preventDefault(); } });
    window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
    window.addEventListener("dragleave", function () { depth = Math.max(0, depth - 1); if (!depth) document.body.classList.remove("drop-on"); });
    window.addEventListener("drop", function (e) {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth = 0; document.body.classList.remove("drop-on");
      var f = e.dataTransfer.files && e.dataTransfer.files[0]; if (!f) return;
      busy("Copying \u201C" + f.name + "\u201D into the editor\u2026 0%");
      var xhr = new XMLHttpRequest();
      xhr.open("POST", url("/api/upload", { name: f.name }));
      xhr.upload.onprogress = function (ev) { if (ev.lengthComputable) busy("Copying \u201C" + f.name + "\u201D into the editor\u2026 " + Math.round(ev.loaded / ev.total * 100) + "%"); };
      xhr.onload = function () {
        var j = {}; try { j = JSON.parse(xhr.responseText); } catch (x) { /* keep empty */ }
        if (xhr.status === 200 && j.path) loadFile(j.path, true); else busy("Could not use that file: " + (j.error || "upload failed") + (j.hint ? " (" + j.hint + ")" : ""));
      };
      xhr.onerror = function () { busy("Upload failed. Use Open file\u2026 instead."); };
      xhr.send(f);
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
      var row = el("div", "inline"), cur = el("input"); cur.type = "text"; cur.id = "tool-input"; cur.value = S.path || ""; cur.placeholder = "Open a video first, or browse";
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
        var row = el("div", "row"), b = el("button", "btn small", "Open result in editor");
        b.addEventListener("click", function () { loadFile(r.output); }); row.appendChild(b); box.appendChild(row);
      }
      if (r.info && r.info.outputs && r.info.outputs.length > 1) box.appendChild(el("pre", "", r.info.outputs.join("\n")));
    }
    var show = r.info && (!r.output || t.read_only) ? r.info : null;
    if (show) box.appendChild(el("pre", "", JSON.stringify(show, null, 2)));
  }

  // ---------------------------------------------------------------- start
  function init() {
    api("/api/config").then(function (c) {
      S.config = c;
      var sp = $("in-speed"); c.speeds.forEach(function (v) { var o = el("option", "", v + "×" + (v === 1 ? " (normal)" : "")); o.value = v; if (v === 1) o.selected = true; sp.appendChild(o); });
      var pr = $("in-preset"); var none = el("option", "", "No preset (keep as is)"); none.value = ""; pr.appendChild(none);
      c.presets.forEach(function (p) { var o = el("option", "", p); o.value = p; pr.appendChild(o); });
      var open = Q.get("open"); if (open) loadFile(open); else fillRecent($("recent"), $("recent-title"), null);
      $("in-outdir").placeholder = "Same folder as the video";
      layoutStage(); renderAll();
    }).catch(function (e) { busy("Cannot reach the editor server: " + e.message); });
  }
  layoutStage(); drawAll(); init();
})();
