"""Timeline rendering (clips played back to back), project files and the timeline export API."""
import json
import os

import pytest

from conftest import ffprobe, needs_ffmpeg, sha
from hermes_video_editor.core.ffmpeg import probe
from hermes_video_editor.core.result import ToolError
from hermes_video_editor.editor import project as P
from test_editor_server import req, wait_job, srv  # noqa: F401  (fixtures/helpers shared with the server tests)

pytestmark = needs_ffmpeg


def clip(media, key, a, b):
    return {"path": str(media[key]), "in": a, "out": b}


def test_graph_is_pure_and_shaped(media):
    clips = P.sanitize_clips([clip(media, "clip", 0.5, 2.5), clip(media, "silent", 0, 1)], [str(media["dir"])])
    w, h, fps = P.canvas_for(clips)
    assert (w, h, fps) == (640, 360, 25.0)
    inputs, graph, has_audio = P.build_render_graph(clips, w, h, fps)
    assert has_audio and inputs.count("-i") == 2 and inputs[:4] == ["-ss", "0.500", "-t", "2.000"]
    assert "anullsrc" in graph and "concat=n=2:v=1:a=1[vo][ao]" in graph        # silent clip gets generated silence
    _, graph_v, audio_v = P.build_render_graph(P.sanitize_clips([clip(media, "silent", 0, 1)], [str(media["dir"])]), 320, 240, 25)
    assert not audio_v and "[ao]" not in graph_v


def test_sanitize_clips_rules(media, tmp_path):
    roots = [str(media["dir"])]
    with pytest.raises(ToolError):
        P.sanitize_clips([], roots)
    with pytest.raises(ToolError):
        P.sanitize_clips([{"path": "/etc/passwd", "in": 0, "out": 1}], roots)
    with pytest.raises(ToolError):
        P.sanitize_clips([{"path": str(media["clip"]), "in": "a", "out": 1}], roots)
    with pytest.raises(ToolError):
        P.sanitize_clips([{"path": str(media["clip"]), "in": 3, "out": 3.01}], roots)
    ok = P.sanitize_clips([{"path": str(media["clip"]), "in": -5, "out": 99}], roots)       # clamped to the file
    assert ok[0]["in"] == 0 and ok[0]["out"] == pytest.approx(4, abs=0.2)


def test_render_mixed_sources(media, tmp_path):
    roots = [str(media["dir"]), str(tmp_path)]
    before = [sha(media[k]) for k in ("clip", "silent", "other")]
    clips = P.sanitize_clips([clip(media, "clip", 1, 3), clip(media, "silent", 0.5, 2), clip(media, "other", 0, 1.5),
                              clip(media, "clip", 0, 0.5)], roots)
    out = P.render_project(clips, tmp_path)
    p = ffprobe(out)
    assert p["duration"] == pytest.approx(2 + 1.5 + 1.5 + 0.5, abs=0.3)
    assert (p["video"]["width"], p["video"]["height"]) == (640, 360) and p["audio"] is not None
    assert str(out).startswith(str(tmp_path)) and out.name == "clip_project.mp4"
    assert [sha(media[k]) for k in ("clip", "silent", "other")] == before


def test_render_audio_only_and_video_only(media, tmp_path):
    clips = P.sanitize_clips([clip(media, "silent", 0, 1), clip(media, "silent", 1, 2)], [str(media["dir"])])
    out = P.render_project(clips, tmp_path)
    assert ffprobe(out)["audio"] is None and ffprobe(out)["duration"] == pytest.approx(2, abs=0.2)


def test_render_same_asset_many_pieces_keeps_duration(media, tmp_path):
    pieces = [clip(media, "clip", i * 0.5, i * 0.5 + 0.4) for i in range(6)]          # 6 x 0.4 s from one file
    out = P.render_project(P.sanitize_clips(pieces, [str(media["dir"])]), tmp_path)
    assert ffprobe(out)["duration"] == pytest.approx(2.4, abs=0.2)


def test_project_roundtrip_and_validation(tmp_path):
    roots = [str(tmp_path)]
    proj = {"version": 1, "name": "demo", "assets": {"a1": {"path": "/x/a.mp4", "name": "a.mp4"}},
            "clips": [{"id": "c1", "asset": "a1", "in": 0, "out": 2.5, "evil": "dropped"}], "extra": 1}
    path = P.save_project(str(tmp_path / "my project"), proj, roots)
    assert path.endswith(".vproj.json") and os.path.isfile(path)
    back = P.load_project(path, roots)
    assert back["clips"] == [{"id": "c1", "asset": "a1", "in": 0.0, "out": 2.5}] and back["name"] == "demo"
    assert "extra" not in back and back["path"] == path
    for bad in (None, {"version": 2}, {"version": 1, "assets": {}, "clips": [{"asset": "zz", "in": 0, "out": 1}]},
                {"version": 1, "assets": {"a": {"path": 5}}, "clips": []},
                {"version": 1, "assets": {"a": {"path": "/x"}}, "clips": [{"asset": "a", "in": "x", "out": 1}]}):
        with pytest.raises(ToolError):
            P.validate_project(bad)
    with pytest.raises(ToolError):
        P.save_project("/etc/evil", proj, roots)
    with pytest.raises(ToolError):
        P.load_project(str(tmp_path / "missing"), roots)


# ---------------------------------------------------------------- HTTP API
def test_timeline_export_api(srv, media, tmp_path):
    srv.add_root(str(tmp_path))
    body = {"clips": [clip(media, "clip", 0, 1.5), clip(media, "other", 0, 1), clip(media, "clip", 2.5, 4)],
            "output_dir": str(tmp_path / "timeline-out")}
    j = wait_job(srv, req(srv, "/api/export", body=body).json()["job"])
    assert j["state"] == "done", j
    res = j["result"]
    assert res["steps"] == ["Rendering the timeline"] and res["duration_s"] == pytest.approx(4.0, abs=0.3)
    assert ffprobe(res["output"])["video"]["width"] == 640
    # the other options still run after the render: speed + preset
    body2 = dict(body, speed=2.0, preset="web_mp4", output_dir=str(tmp_path / "timeline-out2"))
    j2 = wait_job(srv, req(srv, "/api/export", body=body2).json()["job"])
    assert j2["state"] == "done", j2
    assert j2["result"]["steps"][:2] == ["Rendering the timeline", "Changing speed"]
    assert ffprobe(j2["result"]["output"])["duration"] == pytest.approx(2.0, abs=0.4)
    assert os.listdir(str(tmp_path / "timeline-out2")) == [os.path.basename(j2["result"]["output"])]


@pytest.mark.parametrize("clips", [[], "x", [{"path": "/etc/passwd", "in": 0, "out": 1}], [{"path": "nope.mp4", "in": 0, "out": 1}]])
def test_timeline_export_rejects_bad_clips(srv, clips):
    assert req(srv, "/api/export", body={"clips": clips}).status == 400


def test_project_api_save_load_and_ls(srv, tmp_path):
    srv.add_root(str(tmp_path))
    proj = {"version": 1, "name": "p", "assets": {"a": {"path": str(tmp_path / "v.mp4")}}, "clips": [{"id": "c", "asset": "a", "in": 0, "out": 1}]}
    r = req(srv, "/api/project/save", body={"path": str(tmp_path / "saved"), "project": proj})
    assert r.status == 200 and r.json()["path"].endswith("saved.vproj.json")
    loaded = req(srv, "/api/project/load", {"path": r.json()["path"]}).json()
    assert loaded["clips"][0]["out"] == 1.0
    listing = req(srv, "/api/ls", {"path": str(tmp_path), "kind": "project"}).json()
    assert "saved.vproj.json" in {f["name"] for f in listing["files"]}
    assert req(srv, "/api/project/save", body={"path": "/etc/x", "project": proj}).status == 400
    assert req(srv, "/api/project/save", body={"path": str(tmp_path / "bad"), "project": {"version": 9}}).status == 400
    assert req(srv, "/api/project/load", {"path": "/etc/passwd"}).status == 400
    assert req(srv, "/api/project/load", {"path": r.json()["path"]}, token=False).status == 403


# ---------------------------------------------------------------- canvas, background and per-clip transform
import random
import shutil
import subprocess
import textwrap

from conftest import ROOT


def raw_frame(path, vf, t=0.5):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def mean_rgb(data):
    n = len(data) // 3
    return [sum(data[c::3]) / float(n) for c in range(3)]


def render(media, tmp_path, canvas, bg=None, tf=None, key="clip", a=0, b=2):
    c = {"path": str(media[key]), "in": a, "out": b}
    if tf:
        c["tf"] = tf
    clips = P.sanitize_clips([c], [str(media["dir"])])
    return P.render_project(clips, tmp_path / ("o%d" % random.randint(0, 10 ** 9)), canvas=canvas, bg=bg)


def test_geometry_helpers_match_the_javascript_ones(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    rnd = random.Random(7)
    cases = []
    for _ in range(300):
        cases.append({"iw": rnd.choice([320, 321, 640, 1280, 1920, 3840, 1080]), "ih": rnd.choice([180, 241, 360, 720, 1080, 1920, 2160]),
                      "W": rnd.choice([360, 640, 720, 1080, 1920]), "H": rnd.choice([360, 480, 640, 1080, 1350, 1920]),
                      "tf": rnd.choice([None, {}, {"s": rnd.uniform(0.05, 10), "x": rnd.uniform(-3, 3), "y": rnd.uniform(-3, 3)},
                                        {"s": 1, "x": 0.25, "y": -0.1}, {"s": 99, "x": "a"}])})
    canv = [{"aspect": a, "short": s, "fw": rnd.choice([640, 1280, 1920]), "fh": rnd.choice([360, 720, 1080])}
            for a in ["auto", "16:9", "9:16", "1:1", "4:5", "weird"] for s in [360, 480, 720, 1080, 1440, 2160, 123]]
    js = tmp_path / "parity.cjs"
    js.write_text("const T = require(%r); const d = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
                  "console.log(JSON.stringify({rects: d.cases.map(c => T.fgRect(c.iw, c.ih, c.W, c.H, c.tf)), "
                  "sizes: d.canv.map(c => T.canvasSize(c.aspect, c.short, c.fw, c.fh))}))" % str(ROOT / "editor" / "web" / "timeline.js"))
    out = subprocess.run([node, str(js)], input=json.dumps({"cases": cases, "canv": canv}), capture_output=True, text=True, check=True)
    got = json.loads(out.stdout)
    assert got["rects"] == [list(P.fg_rect(c["iw"], c["ih"], c["W"], c["H"], c["tf"])) for c in cases]
    assert got["sizes"] == [list(P.canvas_size(c["aspect"], c["short"], c["fw"], c["fh"])) for c in canv]


def test_sanitizers():
    assert P.sanitize_canvas(None) == {"aspect": "auto", "short": 1080}
    assert P.sanitize_canvas({"aspect": "9:16", "short": 720}) == {"aspect": "9:16", "short": 720}
    assert P.sanitize_canvas({"aspect": "evil", "short": 5}) == {"aspect": "auto", "short": 1080}
    assert P.sanitize_bg({"mode": "color", "color": "#12aBcd"}) == {"mode": "color", "color": "#12aBcd"}
    assert P.sanitize_bg({"mode": "x", "color": "red;rm"}) == {"mode": "blur", "color": "#000000"}
    assert P.clean_tf({"s": 99, "x": float("nan"), "y": -9}) == {"s": 10.0, "x": 0.0, "y": -3.0}


def test_default_transform_on_matching_canvas_is_a_plain_scale(media):
    clips = P.sanitize_clips([clip(media, "clip", 0, 1)], [str(media["dir"])])
    _, graph, _ = P.build_render_graph(clips, 640, 360, 25.0, {"mode": "blur"})
    assert "overlay" not in graph and "boxblur" not in graph                       # fast path: no compositing needed


def test_vertical_canvas_background_modes(media, tmp_path):
    top = "crop=iw:ih*0.12:0:0"                                                    # a strip of the area above the picture
    blur = render(media, tmp_path, {"aspect": "9:16", "short": 360}, {"mode": "blur"})
    black = render(media, tmp_path, {"aspect": "9:16", "short": 360}, {"mode": "black"})
    red = render(media, tmp_path, {"aspect": "9:16", "short": 360}, {"mode": "color", "color": "#ff0000"})
    for out in (blur, black, red):
        v = ffprobe(out)["video"]
        assert (v["width"], v["height"]) == (360, 640)
    assert max(mean_rgb(raw_frame(black, top))) < 20                               # black bars
    assert max(mean_rgb(raw_frame(blur, top))) > 40                                # blurred copy of the picture
    r, g, b = mean_rgb(raw_frame(red, top))
    assert r > 200 and g < 40 and b < 40                                           # chosen colour
    mid = "crop=iw:ih*0.1:0:ih*0.45"                                               # the picture itself is the same in all three
    assert max(mean_rgb(raw_frame(black, mid))) > 40


def test_zoomed_picture_covers_the_canvas_and_stays_cheap(media, tmp_path):
    out = render(media, tmp_path, {"aspect": "9:16", "short": 360}, {"mode": "black"}, {"s": 3.2, "x": 0, "y": 0})
    v = ffprobe(out)["video"]
    assert (v["width"], v["height"]) == (360, 640)
    for region in ("crop=iw:ih*0.1:0:0", "crop=iw:ih*0.1:0:ih*0.9", "crop=iw*0.1:ih:0:0"):
        assert max(mean_rgb(raw_frame(out, region))) > 40, region                 # no black bars anywhere
    huge = render(media, tmp_path, {"aspect": "9:16", "short": 360}, {"mode": "black"}, {"s": 10, "x": 2.5, "y": -2.5})
    assert ffprobe(huge)["duration"] == pytest.approx(2, abs=0.3)                  # mostly off-canvas picture still renders


def test_position_moves_the_picture(media, tmp_path):
    canvas = {"aspect": "9:16", "short": 360}
    centred = render(media, tmp_path, canvas, {"mode": "black"})
    right = render(media, tmp_path, canvas, {"mode": "black"}, {"s": 1, "x": 0.5, "y": 0})
    left_mid = "crop=iw*0.2:ih*0.1:0:ih*0.45"
    assert max(mean_rgb(raw_frame(centred, left_mid))) > 40                       # picture is there when centred
    assert max(mean_rgb(raw_frame(right, left_mid))) < 20                         # moved right: the left edge is background
    gone = render(media, tmp_path, canvas, {"mode": "black"}, {"s": 1, "x": 3, "y": 0})
    assert max(mean_rgb(raw_frame(gone, "crop=iw:ih*0.1:0:ih*0.45"))) < 20        # moved completely off canvas: background only


def test_per_clip_transforms_in_one_timeline(media, tmp_path):
    clips = P.sanitize_clips([dict(clip(media, "clip", 0, 1.5), tf={"s": 1, "x": 0, "y": 0}),
                              dict(clip(media, "clip", 1.5, 3), tf={"s": 3.2, "x": 0, "y": 0}),
                              dict(clip(media, "silent", 0, 1), tf={"s": 0.5, "x": -0.2, "y": 0.1})], [str(media["dir"])])
    out = P.render_project(clips, tmp_path / "multi", canvas={"aspect": "9:16", "short": 360}, bg={"mode": "color", "color": "#0000ff"})
    p = ffprobe(out)
    assert (p["video"]["width"], p["video"]["height"]) == (360, 640) and p["duration"] == pytest.approx(4.0, abs=0.3) and p["audio"]
    first, second = "crop=iw:ih*0.1:0:0", "crop=iw:ih*0.1:0:0"
    r1, g1, b1 = mean_rgb(raw_frame(out, first, t=0.5))
    assert b1 > 200 and r1 < 60                                                    # clip 1: blue bars on top
    r2 = mean_rgb(raw_frame(out, second, t=2.0))
    assert not (r2[2] > 200 and r2[0] < 60)                                        # clip 2 is zoomed to cover: no blue


def test_project_file_keeps_canvas_background_and_transforms(tmp_path):
    roots = [str(tmp_path)]
    proj = {"version": 1, "name": "t", "assets": {"a": {"path": "/x/a.mp4"}}, "canvas": {"aspect": "9:16", "short": 720},
            "bg": {"mode": "color", "color": "#223344"},
            "clips": [{"id": "c1", "asset": "a", "in": 0, "out": 2, "tf": {"s": 2, "x": 0.1, "y": -0.2}},
                      {"id": "c2", "asset": "a", "in": 2, "out": 3}]}
    back = P.load_project(P.save_project(str(tmp_path / "t"), proj, roots), roots)
    assert back["canvas"] == {"aspect": "9:16", "short": 720} and back["bg"] == {"mode": "color", "color": "#223344"}
    assert back["clips"][0]["tf"] == {"s": 2.0, "x": 0.1, "y": -0.2} and "tf" not in back["clips"][1]
    old = P.validate_project({"version": 1, "assets": {}, "clips": []})              # projects from Etappe 1 still open
    assert old["canvas"] == {"aspect": "auto", "short": 1080} and old["bg"]["mode"] == "blur"


def test_export_api_with_canvas_and_transform(srv, media, tmp_path):
    srv.add_root(str(tmp_path))
    body = {"clips": [dict(clip(media, "clip", 0, 2), tf={"s": 1.5, "x": 0.1, "y": 0})], "canvas": {"aspect": "1:1", "short": 360},
            "bg": {"mode": "black"}, "output_dir": str(tmp_path / "canvas-out")}
    j = wait_job(srv, req(srv, "/api/export", body=body).json()["job"])
    assert j["state"] == "done", j
    v = ffprobe(j["result"]["output"])["video"]
    assert (v["width"], v["height"]) == (360, 360)
    bad = req(srv, "/api/export", body=dict(body, canvas={"aspect": "9:16; rm -rf", "short": "x"}, bg={"mode": "color", "color": "javascript:1"}))
    assert bad.status == 200                                                        # unknown values fall back to safe defaults
    wait_job(srv, bad.json()["job"])


# ---------------------------------------------------------------- text layer and audio track
from hermes_video_editor.core.ffmpeg import has_filter

needs_drawtext = pytest.mark.skipif(not (shutil.which("ffmpeg") and has_filter("drawtext")), reason="ffmpeg built without drawtext")


def max_volume(path, ss, t, af=None):
    cmd = ["ffmpeg", "-hide_banner", "-ss", str(ss), "-t", str(t), "-i", str(path), "-vn"]
    cmd += ["-af", (af + "," if af else "") + "volumedetect", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    return float(err.split("max_volume:")[1].split("dB")[0])


@pytest.fixture(scope="module")
def tone(media):
    f = media["dir"] / "tone1k.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=4", "-c:a", "libmp3lame", str(f)], check=True)
    return f


def test_sanitize_texts_and_audios(media, tone):
    ok = P.sanitize_texts([{"text": "Hi\x00 there\x07", "start": -3, "dur": 99999, "x": 9, "color": "red;rm", "size": 0}])
    assert ok[0]["text"] == "Hi there" and ok[0]["start"] == 0 and ok[0]["dur"] == 3600 and ok[0]["x"] == 1.5 and ok[0]["color"] == "#ffffff" and ok[0]["size"] == 0.01
    assert P.sanitize_texts([{"text": "   "}, {"text": ""}]) == [] and P.sanitize_texts(None) == []
    with pytest.raises(ToolError):
        P.sanitize_texts([{"text": "x"}] * 201)
    roots = [str(media["dir"])]
    a = P.sanitize_audios([{"path": str(tone), "in": -1, "out": 99, "start": 2, "vol": -99, "fi": 1, "fo": 2, "duck": 1}], roots)
    assert a[0]["in"] == 0 and a[0]["out"] == pytest.approx(4, abs=0.2) and a[0]["vol"] == -60 and a[0]["duck"] is True
    for bad in ([{"path": str(media["silent"]), "in": 0, "out": 1}], [{"path": "/etc/passwd"}], [{"path": str(tone), "in": 3, "out": 3.01}], "x"):
        with pytest.raises(ToolError):
            P.sanitize_audios(bad, roots)


def test_graph_with_text_and_audio_is_shaped(media, tone, tmp_path):
    roots = [str(media["dir"])]
    clips = P.sanitize_clips([clip(media, "gap", 0, 4)], roots)
    audios = P.sanitize_audios([{"path": str(tone), "in": 0, "out": 3, "start": 0.5, "vol": -8, "fi": 1, "fo": 1, "duck": True},
                                {"path": str(tone), "in": 0, "out": 2, "start": 0, "vol": 0, "duck": False}], roots)
    texts = P.sanitize_texts([{"text": "100% 'Größe': a,b", "start": 1, "dur": 2, "box": True}])
    inputs, graph, has_audio = P.build_render_graph(clips, 320, 240, 25.0, None, texts, audios, tmp_path)
    assert has_audio and inputs.count("-i") == 3
    assert "[vc]drawtext=" in graph and "enable=between(t\\,1.000\\,3.000)" in graph and "expansion=none" in graph
    assert "concat=n=1:v=1:a=1[vc][ac]" in graph and "asplit=2[mn][s0]" in graph        # one ducked item -> main is split once
    assert "sidechaincompress" in graph and "amix=inputs=3:duration=first:normalize=0[amx]" in graph and "alimiter" in graph
    assert "adelay=500|500" in graph and "afade=t=in:st=0:d=1.0" in graph and "afade=t=out:st=2.000:d=1.0" in graph
    assert (tmp_path / "text0.txt").read_text(encoding="utf-8") == "100% 'Größe': a,b"   # text goes through a file, unescaped


@needs_drawtext
def test_text_appears_only_in_its_time_window(media, tmp_path):
    clips = P.sanitize_clips([clip(media, "clip", 0, 3)], [str(media["dir"])])
    texts = P.sanitize_texts([{"text": "HELLO\nWorld 100%: 'x'", "start": 1.0, "dur": 1.0, "x": 0.5, "y": 0.5, "size": 0.2, "color": "#ff0000",
                               "box": True, "boxColor": "#000000", "boxOpacity": 1}])
    out = P.render_project(clips, tmp_path / "txt", texts=texts)
    centre = "crop=iw*0.5:ih*0.3:iw*0.25:ih*0.35"
    plain = P.render_project(clips, tmp_path / "plain")
    def diff(t):
        a, b = raw_frame(plain, centre, t), raw_frame(out, centre, t)
        return sum(1 for x, y in zip(a, b) if abs(x - y) > 60)
    assert diff(0.4) < 200 and diff(2.6) < 200           # before and after the window: identical picture
    assert diff(1.5) > 3000                              # inside the window: a lot of text and box pixels
    assert ffprobe(out)["duration"] == pytest.approx(3, abs=0.3)


def test_audio_item_starts_at_its_time_with_level_and_fades(media, tone, tmp_path):
    roots = [str(media["dir"])]
    clips = P.sanitize_clips([clip(media, "silent", 0, 3)], roots)                    # picture without sound
    audios = P.sanitize_audios([{"path": str(tone), "in": 0, "out": 2, "start": 1.0, "vol": -6, "fi": 0, "fo": 0.5, "duck": False}], roots)
    out = P.render_project(clips, tmp_path / "aud", audios=audios)
    p = ffprobe(out)
    assert p["audio"] is not None and p["duration"] == pytest.approx(3.0, abs=0.3)
    long = P.render_project(clips, tmp_path / "long", audios=P.sanitize_audios(
        [{"path": str(tone), "in": 0, "out": 4, "start": 1.0, "vol": 0, "fi": 0, "fo": 0, "duck": False}], roots))
    assert ffprobe(long)["duration"] == pytest.approx(3.0, abs=0.3)                  # audio longer than the picture is cut
    assert max_volume(out, 0, 0.8) < -60                                              # nothing before the start time
    mid = max_volume(out, 1.3, 1.0)
    loud = P.render_project(clips, tmp_path / "aud0", audios=P.sanitize_audios(
        [{"path": str(tone), "in": 0, "out": 2, "start": 1.0, "vol": 0, "fi": 0, "fo": 0, "duck": False}], roots))
    assert mid == pytest.approx(max_volume(loud, 1.3, 1.0) - 6, abs=1.0)              # -6 dB relative to the untouched level
    assert max_volume(out, 2.8, 0.2) < mid - 6                                       # fade-out at the end of the timeline window


def test_ducking_lowers_the_music_while_the_clip_speaks(media, tone, tmp_path):
    roots = [str(media["dir"])]
    clips = P.sanitize_clips([clip(media, "gap", 0, 4)], roots)                       # tone 0-1 s and 2.5-4 s, silence 1-2.5 s
    band = "bandpass=f=1000:width_type=h:w=150"                                        # isolate the 1 kHz music from the 500 Hz speech
    def levels(duck):
        a = P.sanitize_audios([{"path": str(tone), "in": 0, "out": 4, "start": 0, "vol": 0, "duck": duck}], roots)
        out = P.render_project(clips, tmp_path / ("duck%s" % duck), audios=a)
        return max_volume(out, 0.4, 0.5, band), max_volume(out, 1.4, 0.8, band)
    speech_on, gap_on = levels(True)
    speech_off, gap_off = levels(False)
    assert gap_on - speech_on > 3                                                      # music comes back up in the pause
    assert abs(gap_off - speech_off) < 1.5                                             # without ducking it stays level


def test_text_and_audio_via_api_and_project_file(srv, media, tone, tmp_path):
    srv.add_root(str(tmp_path))
    body = {"clips": [clip(media, "silent", 0, 2)], "texts": [{"text": "Title", "start": 0.2, "dur": 1, "size": 0.1}],
            "audios": [{"path": str(tone), "in": 0, "out": 3, "start": 0.5, "vol": -9, "fo": 0.5, "duck": False}],
            "output_dir": str(tmp_path / "layers")}
    j = wait_job(srv, req(srv, "/api/export", body=body).json()["job"])
    assert j["state"] == "done", j
    assert ffprobe(j["result"]["output"])["audio"] is not None
    assert req(srv, "/api/export", body=dict(body, audios=[{"path": "/etc/passwd"}])).status == 400
    assert req(srv, "/api/export", body=dict(body, texts="x")).status == 400
    proj = {"version": 1, "assets": {"a": {"path": str(media["silent"])}, "m": {"path": str(tone)}},
            "clips": [{"id": "c", "asset": "a", "in": 0, "out": 2}],
            "texts": [{"id": "t1", "text": "Hi", "start": 0, "dur": 2, "x": 0.4, "color": "#00ff00"}],
            "audios": [{"id": "m1", "asset": "m", "in": 0, "out": 3, "start": 0.5, "vol": -9, "fi": 0, "fo": 0.5, "duck": True}]}
    back = P.load_project(P.save_project(str(tmp_path / "layers"), proj, [str(tmp_path)]), [str(tmp_path)])
    assert back["texts"][0]["color"] == "#00ff00" and back["texts"][0]["x"] == 0.4
    assert back["audios"][0]["asset"] == "m" and back["audios"][0]["duck"] is True and back["audios"][0]["vol"] == -9
    with pytest.raises(ToolError):
        P.validate_project(dict(proj, audios=[{"id": "x", "asset": "nope", "in": 0, "out": 1}]))
    assert P.validate_project({"version": 1, "assets": {}, "clips": []})["texts"] == []     # older projects still open
