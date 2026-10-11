"use strict";
/* Media library (left column, like the media bin of a phone editor): every file that was added is a card. A click puts it where it
   belongs: videos at the end of the main track, sounds and stickers at the playhead. */
(function () {
  var V = window.VE;
  if (!V || !V.layers) return;
  var S = V.S, $ = V.$, el = V.el, L = V.layers;

  function kind(a) { return a.picture ? "picture" : (a.hasVideo ? "video" : "audio"); }
  function useAsset(a) {
    if (a.state === "missing") { V.flash(a.name + " was not found."); return; }
    var k = kind(a);
    if (k === "video") V.addClipFromPath(a.path);
    else if (k === "audio") V.addAudioAsset(a);
    else V.addPictureAsset(a);
  }
  function usage(a) {
    var n = S.clips.filter(function (c) { return c.asset === a.id; }).length + S.audios.filter(function (x) { return x.asset === a.id; }).length + S.overlays.filter(function (o) { return o.asset === a.id; }).length;
    return n ? n + "× used" : "not used yet";
  }
  function thumb(a, box) {
    var k = kind(a);
    if (k === "picture") { var im = el("img"); im.alt = ""; im.src = V.url("/api/image", { path: a.path }); im.loading = "lazy"; box.appendChild(im); return; }
    if (k === "video" && a.thumbs && a.cacheId) {
      var n = a.thumbs.count; box.style.backgroundImage = "url('" + V.url("/api/cache", { id: a.cacheId, name: a.thumbs.name }) + "')";
      box.style.backgroundSize = (n * 100) + "% 100%"; box.style.backgroundPosition = "0 0"; return;
    }
    box.appendChild(el("span", "lib-ico", k === "audio" ? "♪" : "🎬"));
  }
  function render() {
    var grid = $("lib-grid"), ids = Object.keys(S.assets);
    var sig = ids.map(function (id) { var a = S.assets[id]; return id + ":" + a.state + ":" + (a.thumbs ? 1 : 0) + ":" + usage(a); }).join("|");
    $("lib-empty").hidden = ids.length > 0;
    if (grid.getAttribute("data-sig") === sig) return;                       // nothing visible changed: keep the cards (and any drag in progress)
    grid.setAttribute("data-sig", sig); grid.textContent = "";
    ids.forEach(function (id) {
      var a = S.assets[id], k = kind(a), card = el("button", "lib-card" + (a.state === "missing" ? " missing" : ""));
      card.type = "button"; card.title = a.path + "\n" + (k === "video" ? "Click: add to the end of the timeline" : k === "audio" ? "Click: add sound at the playhead" : "Click: add as a sticker at the playhead");
      card.setAttribute("data-asset", id);
      var t = el("span", "lib-thumb"); thumb(a, t); card.appendChild(t);
      card.appendChild(el("span", "lib-name", a.name));
      card.appendChild(el("span", "lib-meta", (k === "picture" ? (a.animated ? "GIF" : "Picture") : (k === "audio" ? "Sound " : "Video ") + V.fmt(a.dur || 0, false)) + " · " + usage(a)));
      card.addEventListener("click", function () { useAsset(a); });
      grid.appendChild(card);
    });
  }
  $("lib-import").addEventListener("click", function () { $("btn-open").click(); });
  $("lib-picture").addEventListener("click", function () { $("btn-ov-pic").click(); });
  $("lib-text").addEventListener("click", function () { $("btn-text-add").click(); });
  $("lib-shape").addEventListener("click", function () { $("btn-shape-add").click(); });
  $("lib-bg").addEventListener("click", function () { $("btn-bg-strip-add").click(); });
  $("lib-subs").addEventListener("click", function () { V.tab("text"); $("btn-captions").scrollIntoView({ block: "center" }); });
  function wide() { return window.innerWidth >= 1180; }
  function setHidden(h) { document.body.classList.toggle("lib-hidden", h); $("btn-library").classList.toggle("on", !h); setTimeout(function () { window.dispatchEvent(new Event("resize")); }, 0); }
  $("btn-library").addEventListener("click", function () { setHidden(!document.body.classList.contains("lib-hidden")); });
  setHidden(!wide());
  var o = { render: L.render };
  L.render = function () { o.render(); render(); };
  V.renderAll();
})();
