"use strict";
/* Click on the preview to select what is under the mouse: the front-most text, video on top, shape or the clip itself,
   and start dragging it right away. Everything that was drawn registers itself in VE.hits while the preview is painted. */
(function () {
  var V = window.VE;
  if (!V) return;
  var $ = V.$;

  function topAt(x, y) {
    var best = null;
    V.hits.forEach(function (h) {
      var r = h.rect;
      if (x >= r[0] && x <= r[0] + r[2] && y >= r[1] && y <= r[1] + r[3] && (!best || h.z >= best.z)) best = h;
    });
    return best;
  }
  $("stage").addEventListener("mousedown", function (e) {
    if (e.button !== 0 || V.playing()) return;
    if (e.target.closest && e.target.closest(".gh")) return;                                // corner handles of the clip keep their own handling
    var box = $("stage").getBoundingClientRect(), x = e.clientX - box.left, y = e.clientY - box.top;
    var hit = topAt(x, y);
    // a click inside the frame that is already selected just drags it (its own gizmo handles that)
    if (hit && e.target.id === hit.gizmo && !$(hit.gizmo).hidden) return;
    e.stopPropagation(); e.preventDefault();                                                  // we decide who gets this click (capture phase: before any gizmo)
    if (!hit) { V.clearSel("none"); V.renderAll(); return; }
    hit.select(); V.renderAll();
    var g = $(hit.gizmo);
    if (g && !g.hidden) g.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0, clientX: e.clientX, clientY: e.clientY }));
  }, true);
})();
