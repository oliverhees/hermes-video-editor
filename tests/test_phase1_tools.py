import json
import shutil

import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha, HANDLERS

pytestmark = needs_ffmpeg


def test_doctor():
    r = call("lk_media_doctor")
    assert r["ok"], r
    assert r["info"]["encoders"]["libx264"] and r["info"]["encoders"]["aac"]
    assert "ffmpeg_version" in r["info"]


def test_probe(media):
    r = call("lk_media_probe", input=str(media["clip"]))
    assert r["ok"]
    i = r["info"]
    assert i["video"]["width"] == 640 and i["video"]["height"] == 360
    assert i["video"]["fps"] == 25.0 and i["has_audio"] and i["audio"][0]["codec"] == "aac"
    assert r["duration_s"] == pytest.approx(4, abs=0.2)


def test_probe_silent_and_odd(media):
    assert call("lk_media_probe", input=str(media["silent"]))["info"]["has_audio"] is False
    assert call("lk_media_probe", input=str(media["odd"]))["info"]["video"]["width"] == 321


def test_probe_errors(tmp_path):
    assert call("lk_media_probe", input=str(tmp_path / "nope.mp4"))["ok"] is False
    txt = tmp_path / "a.txt"
    txt.write_text("hello")
    r = call("lk_media_probe", input=str(txt))
    assert r["ok"] is False and r["error"]
    assert call("lk_media_probe")["ok"] is False


def test_trim_accurate(media, out_dir):
    before = sha(media["clip"])
    r = call("lk_trim", input=str(media["clip"]), start=1, end="00:03", output_dir=str(out_dir))
    assert r["ok"], r
    p = ffprobe(r["output"])
    assert p["duration"] == pytest.approx(2.0, abs=0.15)
    assert p["video"]["width"] == 640 and p["audio"] is not None
    assert r["output"].endswith("clip_trim.mp4")
    assert sha(media["clip"]) == before


def test_trim_fast_duration(media, out_dir):
    r = call("lk_trim", input=str(media["clip"]), start=0, duration=2, mode="fast", output_dir=str(out_dir))
    assert r["ok"], r
    assert ffprobe(r["output"])["duration"] == pytest.approx(2.0, abs=0.6)


def test_trim_silent_clip(media, out_dir):
    r = call("lk_trim", input=str(media["silent"]), start=0.5, duration=1, output_dir=str(out_dir))
    assert r["ok"], r
    assert ffprobe(r["output"])["audio"] is None


def test_trim_odd_dimensions(media, out_dir):
    r = call("lk_trim", input=str(media["odd"]), duration=1, output_dir=str(out_dir))
    assert r["ok"], r
    v = ffprobe(r["output"])["video"]
    assert (v["width"], v["height"]) == (320, 240)


def test_trim_unicode_spaces_path(media, out_dir):
    r = call("lk_trim", input=str(media["tricky"]), duration=1)
    assert r["ok"], r
    assert "mein Ordner ünï" in r["output"] and "clip äöü_trim" in r["output"]


def test_trim_collision_suffix(media, out_dir):
    a = call("lk_trim", input=str(media["clip"]), duration=1, output_dir=str(out_dir))
    b = call("lk_trim", input=str(media["clip"]), duration=1, output_dir=str(out_dir))
    c = call("lk_trim", input=str(media["clip"]), duration=1, output_dir=str(out_dir), overwrite=True)
    assert a["output"].endswith("clip_trim.mp4") and b["output"].endswith("clip_trim_1.mp4")
    assert c["output"] == a["output"]


@pytest.mark.parametrize("kw", [
    {"start": "abc"}, {"start": 3, "end": 2}, {"start": 99}, {"end": 2, "duration": 1},
    {"duration": 0}, {"start": "1:99"}, {"mode": "weird"}, {"crf": 99}, {"timeout_s": 0},
])
def test_trim_bad_params(media, out_dir, kw):
    r = call("lk_trim", input=str(media["clip"]), output_dir=str(out_dir), **kw)
    assert r["ok"] is False and r["error"]
    assert not out_dir.exists() or not list(out_dir.iterdir())


def test_output_cannot_be_input(media):
    r = call("lk_trim", input=str(media["clip"]), output=str(media["clip"]), overwrite=True, duration=1)
    assert r["ok"] is False


def test_missing_ffmpeg(media, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    for name, args in [("lk_media_doctor", {}), ("lk_media_probe", {"input": str(media["clip"])}),
                       ("lk_trim", {"input": str(media["clip"]), "duration": 1})]:
        r = call(name, **args)
        assert r["ok"] is False
        assert "winget" in r["hint"] and "apt" in r["hint"] and "brew" in r["hint"]


def test_timeout_kills_process():
    from hermes_video_editor.core.ffmpeg import run_ffmpeg
    from hermes_video_editor.core.result import ToolError
    with pytest.raises(ToolError) as exc:
        run_ffmpeg(["-f", "lavfi", "-i", "testsrc=duration=600:size=1280x720:rate=30",
                    "-f", "null", "-"], timeout_s=1)
    assert "timed out" in exc.value.message


def test_handler_never_raises():
    for h in HANDLERS.values():
        for bad in (None, "str", 5, [], {"input": 12345}, {"input": None}):
            assert isinstance(json.loads(h(bad)), dict)


class FakeCtx:
    def __init__(self):
        self.tools, self.skills = {}, {}

    def register_tool(self, name, toolset, schema, handler, **kw):
        assert name not in self.tools
        self.tools[name] = (toolset, schema, handler)

    def register_skill(self, name, path):
        self.skills[name] = path


def test_register_valid_schemas():
    import hermes_video_editor
    ctx = FakeCtx()
    hermes_video_editor.register(ctx)
    assert ctx.tools
    for name, (toolset, schema, handler) in ctx.tools.items():
        assert name.startswith("lk_") and toolset == "video_editor"
        assert schema["name"] == name and schema["description"]
        assert schema["parameters"]["type"] == "object"
        assert callable(handler)
