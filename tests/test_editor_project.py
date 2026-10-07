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
