"use strict";
/* Automatic subtitles: the optional local speech recogniser (faster-whisper) turns the speech of the clips into texts on the timeline.
   Nothing leaves this computer. The texts are bundled into a scene called "Captions" so they can be moved together. */
(function () {
  var V = window.VE;
  if (!V || !V.layers || !V.tracks) return;
  var S = V.S, TL = V.TL, $ = V.$, T = V.tracks;
  var cache = {};                    // asset id + language + model -> cues (one run per file)

  function setBusy(on, msg) { $("btn-captions").disabled = on; $("cap-state").textContent = msg || ""; }
  function transcribe(asset, lang, model) {
    var key = asset.id + "|" + lang + "|" + model;
    if (cache[key]) return Promise.resolve(cache[key]);
    return V.api("/api/captions", null, { path: asset.path, language: lang || undefined, model: model }).then(function (r) {
      return new Promise(function (resolve, reject) {
        (function poll() {
          V.api("/api/job", { id: r.job }).then(function (j) {
            if (j.state === "running") return setTimeout(poll, 800);
            if (j.state === "error") { var e = new Error(j.error.error); e.hint = j.error.hint; return reject(e); }
            cache[key] = j.result; resolve(j.result);
          }).catch(reject);
        })();
      });
    });
  }

  $("btn-captions").addEventListener("click", function () {
    if (!S.clips.length) { V.flash("Add a clip first."); return; }
    var only = $("cap-scope").value === "selected" && S.sel >= 0 ? S.sel : null, lang = $("cap-lang").value, model = $("cap-model").value;
    var ids = {}; S.clips.forEach(function (c, i) { var a = V.assetFor(c.asset); if (a && a.hasAudio && !c.freeze && (only == null || only === i) && !(c.adj && c.adj.mute)) ids[c.asset] = true; });
    var list = Object.keys(ids); if (!list.length) { V.flash("These clips have no sound to listen to."); return; }
    var left = list.length;
    setBusy(true, "Listening… (the first run can take a while)");
    var found = [];
    list.reduce(function (p, id) {
      return p.then(function () {
        return transcribe(V.assetFor(id), lang, model).then(function (res) { found = found.concat(TL.captionTimes(S.clips, id, res.cues, only)); setBusy(true, "Listening… " + (--left) + " file(s) left"); });
      });
    }, Promise.resolve()).then(function () {
      found.sort(function (a, b) { return a.start - b.start; });
      var room = Math.max(0, 200 - S.texts.length);
      if (!found.length) { setBusy(false, "No speech found."); return; }
      var take = found.slice(0, room); if (!take.length) { setBusy(false, "The project already has 200 texts (the limit)."); return; }
      V.commit(function () {
        var end = take[take.length - 1].start + take[take.length - 1].dur, track = T.freeTrack("text", take[0].start, end - take[0].start);
        var texts = take.map(function (c) {
          var t = TL.newText(c.start, c.dur); t.text = c.text; t.size = 0.055; t.y = 0.88; t.box = true; t.boxOpacity = 0.5; t.track = track; return TL.cleanText(t);
        });
        S.texts = S.texts.concat(texts);
        var sc = TL.newScene(take[0].start, end - take[0].start, "Captions", texts.map(function (t) { return t.id; })); sc.track = T.freeTrack("scene", sc.start, sc.dur);
        S.scenes = S.scenes.concat([sc]); V.clearSel("scene"); S.selScene = S.scenes.length - 1;
      });
      setBusy(false, take.length + " subtitle" + (take.length > 1 ? "s" : "") + " added" + (take.length < found.length ? " (limit of 200 texts reached)" : "") + ". Click one to correct it.");
      V.tab("text");
    }).catch(function (e) { setBusy(false, ""); V.flash("Subtitles: " + e.message + (e.hint ? " - " + e.hint : "")); $("cap-state").textContent = e.message + (e.hint ? " - " + e.hint : ""); });
  });
})();
