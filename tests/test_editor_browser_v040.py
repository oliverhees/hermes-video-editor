"""v0.4.0 in a real browser: toolbar, magnet, background strips, the Clip tab (speed, still frame, transition, look), fades, subtitles."""
import json
import sys
import types

import pytest

from conftest import needs_ffmpeg
from test_editor_integration import bbox, browser, state, wait_ready
from test_editor_project import _red, _rgb_at

pytestmark = needs_ffmpeg


def setup(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    page.goto(srv.url(str(media["clip"])))
    wait_ready(page)
    return srv, p, b, page, errors


def blur(page):
    page.evaluate("document.activeElement && document.activeElement.blur()")


def test_toolbar_split_trim_clone_delete_undo(media, tmp_path):
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.evaluate("window.__ve.seek(1.5)")
        page.click("#tb-split")
        assert state(page, "s.clips.map(c => [c.in, c.out])") == [[0, 1.5], [1.5, 4]]
        page.evaluate("window.__ve.seek(2.5)")
        page.click("#tb-trim-start")                                   # everything before the playhead in the selected clip goes away
        assert state(page, "s.clips.map(c => [c.in, c.out])") == [[0, 1.5], [2.5, 4]]
        page.click("#tb-clone")
        assert state(page, "s.clips.length") == 3 and state(page, "s.clips[2].in") == 2.5
        page.click("#tb-undo")
        assert state(page, "s.clips.length") == 2
        page.click("#tb-redo")
        assert state(page, "s.clips.length") == 3
        page.click("#tb-delete")
        assert state(page, "s.clips.length") == 2
        # the same buttons work on a layer item: a text is split at the playhead and cloned
        page.click("#tabs button[data-tab=text]")
        page.evaluate("window.__ve.seek(0.5)")
        page.click("#btn-text-add")
        page.evaluate("window.__ve.seek(1.5)")
        blur(page)
        page.click("#tb-split")
        assert state(page, "s.texts.length") == 2 and state(page, "s.texts[0].dur") == pytest.approx(1.0, abs=0.01)
        page.click("#tb-clone")
        assert state(page, "s.texts.length") == 3
        page.keyboard.press("Control+z")
        assert state(page, "s.texts.length") == 2
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def test_magnet_snaps_items_to_the_playhead_and_can_be_switched_off(media, tmp_path):
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.evaluate("window.__ve.seek(2)")
        page.click("#tabs button[data-tab=text]")
        page.evaluate("window.__ve.seek(0.2)")
        page.click("#btn-text-add")
        page.evaluate("window.__ve.seek(2)")
        zoom = state(page, "s.zoom")
        item = bbox(page, '.litem[data-kind="text"]')
        # drag so that the text's left edge lands 3 px beside the playhead (2 s): the magnet pulls it exactly onto 2 s
        dx = (2 * zoom + 3) - (item["x"] - bbox(page, "#track")["x"])
        page.mouse.move(item["x"] + 20, item["y"] + item["height"] / 2)
        page.mouse.down()
        page.mouse.move(item["x"] + 20 + dx / 2, item["y"] + item["height"] / 2, steps=3)
        page.mouse.move(item["x"] + 20 + dx, item["y"] + item["height"] / 2, steps=3)
        page.mouse.up()
        assert state(page, "s.texts[0].start") == pytest.approx(2.0, abs=0.001)
        page.click("#tb-magnet")
        assert state(page, "s.magnet") is False
        item = bbox(page, '.litem[data-kind="text"]')
        page.mouse.move(item["x"] + 20, item["y"] + item["height"] / 2)
        page.mouse.down()
        page.mouse.move(item["x"] + 20 + 3, item["y"] + item["height"] / 2, steps=2)
        page.mouse.move(item["x"] + 20 + 6, item["y"] + item["height"] / 2, steps=2)
        page.mouse.up()
        assert state(page, "s.texts[0].start") != pytest.approx(2.0, abs=0.001)
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def test_background_strip_lane_edit_and_export(media, tmp_path):
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.click("#tabs button[data-tab=picture]")
        page.select_option("#in-aspect", "9:16")
        page.select_option("#in-short", "360")
        page.select_option("#in-bg", "black")
        page.evaluate("window.__ve.seek(1)")
        page.click("#btn-bg-strip-add")
        assert state(page, "s.bgs.length") == 1 and state(page, "s.selBg") == 0 and page.locator('.litem[data-kind="bg"]').count() == 1
        page.select_option("#in-bg", "color")
        page.evaluate("(() => { const i = document.getElementById('in-bgcolor'); i.value = '#ff0000'; i.dispatchEvent(new Event('change', {bubbles: true})) })()")
        assert state(page, "s.bgs[0].mode") == "color" and state(page, "s.bgs[0].color") == "#ff0000" and state(page, "s.bg.mode") == "black"
        page.evaluate("window.__ve.state.bgs[0].dur = 1.5")
        page.evaluate("window.__ve.seek(1.5)"); page.wait_for_timeout(300)
        px = page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(5, 5, 1, 1).data; return [d[0], d[1], d[2]] })()")
        assert px[0] > 200 and px[1] < 40                                  # the preview shows the strip's colour
        page.evaluate("window.__ve.seek(3.5)"); page.wait_for_timeout(300)
        px = page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(5, 5, 1, 1).data; return [d[0], d[1], d[2]] })()")
        assert max(px) < 30                                                # outside the strip: the project background
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "bgout"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=120000)
        out = next((tmp_path / "bgout").glob("*.mp4"))
        assert _red(_rgb_at(out, 10, 10, 1.8)) and not _red(_rgb_at(out, 10, 10, 3.2))
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def test_clip_tab_speed_still_frame_transition_look_and_export(media, tmp_path):
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.evaluate("window.__ve.seek(2)")
        page.click("#tb-split")
        page.click("#tabs button[data-tab=clip]")
        assert state(page, "s.clips.length") == 2
        # speed of the second clip (selected after the split): 2x halves its time on the timeline
        page.click('#fx-speeds button[data-speed="2"]')
        assert state(page, "s.clips[1].sp") == 2 and state(page, "TL.total(s.clips)") == pytest.approx(3, abs=0.01)
        # still frame at the playhead inside the first clip
        page.evaluate("window.__ve.seek(1)")
        page.fill("#fx-freeze-len", "1.5")
        page.click("#btn-fx-freeze")
        assert state(page, "s.clips.map(c => c.freeze || 0)") == [0, 1.5, 0, 0]
        assert state(page, "TL.total(s.clips)") == pytest.approx(4.5, abs=0.01)
        # transition into the last clip and a look
        page.evaluate("window.__ve.state.sel = 3; window.__ve.seek(3.2)")
        page.click("#tabs button[data-tab=clip]")
        page.select_option("#fx-tr", "slideleft")
        assert state(page, "s.clips[3].tr.type") == "slideleft"
        page.evaluate("(() => { const i = document.getElementById('fx-br'); i.value = 40; i.dispatchEvent(new Event('input', {bubbles: true})); i.dispatchEvent(new Event('change', {bubbles: true})) })()")
        assert state(page, "s.clips[3].adj.br") == pytest.approx(0.4)
        assert page.locator(".clip .trz").count() == 1
        page.keyboard.press("Control+z")
        page.evaluate("document.activeElement && document.activeElement.blur()")
        # export: the file has the length of the layout (transition overlaps the previous clip)
        total = state(page, "TL.total(s.clips)")
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "fx"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=180000)
        from conftest import ffprobe
        out = next((tmp_path / "fx").glob("*.mp4"))
        assert ffprobe(out)["duration"] == pytest.approx(total, abs=0.35)
        # the project file keeps all of it
        page.click("#btn-saveas")
        page.fill("#dlg-name", "fx")
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        for _ in range(50):
            if state(page, "s.dlgProjectPath") == str(tmp_path):
                break
            page.wait_for_timeout(100)
        page.click("#dlg-usefolder")
        saved = tmp_path / "fx.vproj.json"
        for _ in range(50):
            if saved.exists():
                break
            page.wait_for_timeout(100)
        data = json.loads(saved.read_text())
        assert data["clips"][3]["sp"] == 2 and data["clips"][1]["freeze"] == 1.5 and data["clips"][3]["tr"]["type"] == "slideleft"
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def test_fades_are_edited_and_exported(media, tmp_path):
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.click("#tabs button[data-tab=shape]")
        page.evaluate("window.__ve.seek(1)")
        page.click("#sh-p-full")
        page.evaluate("(() => { const i = document.getElementById('sh-fi'); i.value = 1; i.dispatchEvent(new Event('input', {bubbles: true})); i.dispatchEvent(new Event('change', {bubbles: true})) })()")
        assert state(page, "s.shapes[0].fi") == 1
        page.evaluate("window.__ve.seek(1.4)"); page.wait_for_timeout(300)
        half = page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(Math.round(c.width / 2), Math.round(c.height / 2), 1, 1).data; return d[0] + d[1] + d[2] })()")
        page.evaluate("window.__ve.seek(2.5)"); page.wait_for_timeout(300)
        full = page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(Math.round(c.width / 2), Math.round(c.height / 2), 1, 1).data; return d[0] + d[1] + d[2] })()")
        assert half > full                                                 # black field fading in: the picture is still partly visible
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def _fake_whisper(monkeypatch):
    mod = types.ModuleType("faster_whisper")

    class Seg:
        def __init__(self, s, e, t):
            self.start, self.end, self.text = s, e, t

    class WhisperModel:
        def __init__(self, name, **kw):
            pass

        def transcribe(self, path, **kw):
            return iter([Seg(0.0, 1.0, " Hallo Welt"), Seg(1.2, 2.5, " zweiter Satz"), Seg(3.0, 3.9, " dritter")]), types.SimpleNamespace(language="de")

    mod.WhisperModel = WhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_automatic_subtitles_become_texts_in_a_scene(media, tmp_path, monkeypatch):
    _fake_whisper(monkeypatch)
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.evaluate("window.__ve.seek(1)")
        page.click("#tb-split")                                         # second clip starts at 1 s of the source...
        page.evaluate("window.__ve.state.clips[1].sp = 2; window.__ve.state.clips[1] = window.__ve.TL.copy(window.__ve.state.clips[1], {sp: 2})")
        page.click("#tabs button[data-tab=text]")
        page.click("#btn-captions")
        for _ in range(200):
            if state(page, "s.texts.length") > 0:
                break
            page.wait_for_timeout(100)
        texts = state(page, "s.texts.map(t => [t.text, t.start, t.dur, t.track])")
        # cue 1 (0-1 s) lies in clip 1 (0-1 s) at its place; the cues after 1 s sit in the 2x clip: start = 1 + (cue - 1) / 2
        assert [t[0] for t in texts] == ["Hallo Welt", "zweiter Satz", "dritter"]
        assert texts[0][1] == pytest.approx(0, abs=0.01) and texts[1][1] == pytest.approx(1.1, abs=0.01) and texts[1][2] == pytest.approx(0.65, abs=0.01)
        assert texts[2][1] == pytest.approx(2.0, abs=0.01)
        assert state(page, "s.scenes[0].name") == "Captions" and len(state(page, "s.scenes[0].items")) == 3
        assert not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()


def test_captions_endpoint_reports_missing_model_clearly(media, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    srv, p, b, page, errors = setup(media, tmp_path)
    try:
        page.click("#tabs button[data-tab=text]")
        page.click("#btn-captions")
        for _ in range(100):
            if "faster-whisper" in page.inner_text("#cap-state"):
                break
            page.wait_for_timeout(100)
        assert "faster-whisper" in page.inner_text("#cap-state") and page.is_enabled("#btn-captions")
        assert state(page, "s.texts.length") == 0
    finally:
        b.close(); p.stop(); srv.stop()
