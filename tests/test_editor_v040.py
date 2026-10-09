"""v0.4.0 render features: background strips, fades, clip adjustments, speed, still frames and transitions."""
import pytest

from conftest import ffprobe, needs_ffmpeg
from hermes_video_editor.editor import project as P
from test_editor_project import _red, _rgb_at, clip, mean_rgb, raw_frame

pytestmark = needs_ffmpeg
CANVAS = {"aspect": "9:16", "short": 360}          # 360x640: the 16:9 picture leaves bars above and below it


def sanitized(media, spec):
    return P.sanitize_clips(spec, [str(media["dir"])])


def test_sanitize_bgsegs_and_clip_fields(media):
    segs = P.sanitize_bgsegs([{"mode": "color", "color": "#ff0000", "start": -3, "dur": 0, "track": 99}, "junk", {"mode": "nope"}])
    assert segs[0]["start"] == 0 and segs[0]["dur"] == 0.1 and segs[0]["track"] == 11 and segs[1]["mode"] == "blur"
    assert P.sanitize_bgsegs(None) == []
    with pytest.raises(P.ToolError):
        P.sanitize_bgsegs([{}] * 101)
    f = P.clean_clip_fields({"adj": {"br": 5, "ct": -1, "vol": 99, "mute": 1}, "sp": 9, "freeze": 0.01, "tr": {"type": "nope"}})
    assert f["adj"]["br"] == 1 and f["adj"]["ct"] == 0 and f["adj"]["vol"] == 24 and f["adj"]["mute"] is True
    assert f["sp"] == 4 and "freeze" not in f and "tr" not in f
    assert P.clean_clip_fields({"adj": {}, "sp": 1}) == {}                              # defaults are not stored
    clips = sanitized(media, [dict(clip(media, "clip", 3.9, 4), freeze=2)])
    assert clips[0]["freeze"] == 2 and clips[0]["out"] - clips[0]["in"] == pytest.approx(0.1, abs=1e-6)


def test_layout_with_speed_freeze_and_transitions(media):
    cl = [{"in": 0, "out": 4, "sp": 2}, {"in": 0, "out": 3, "tr": {"type": "fade", "dur": 5}}, {"in": 0, "out": 0.1, "freeze": 2, "tr": {"type": "fade", "dur": 0.5}}]
    starts, durs, trs, total = P.clip_layout(cl)
    assert durs == [2, 3, 2] and trs == [0, 1.0, 0.5]        # 1.0 = half of the shorter neighbour (2 s)
    assert starts == [0, 1.0, 3.5] and total == pytest.approx(5.5)


def test_background_strip_shows_only_in_its_window(media, tmp_path):
    clips = sanitized(media, [clip(media, "clip", 0, 4)])
    plain = P.render_project(clips, tmp_path / "plain", canvas=CANVAS, bg={"mode": "black"})
    strips = P.sanitize_bgsegs([{"mode": "color", "color": "#ff0000", "start": 1, "dur": 1.5}])
    out = P.render_project(clips, tmp_path / "strip", canvas=CANVAS, bg={"mode": "black"}, bgs=strips)
    assert ffprobe(out)["duration"] == pytest.approx(4, abs=0.3)
    assert _red(_rgb_at(out, 20, 20, 1.5)) and _red(_rgb_at(out, 20, 620, 1.5))
    assert not _red(_rgb_at(out, 20, 20, 0.4)) and not _red(_rgb_at(out, 20, 20, 3.0))
    assert _rgb_at(out, 180, 320, 1.5) == pytest.approx(_rgb_at(plain, 180, 320, 1.5), abs=12)      # the picture stays on top


def test_background_strips_span_clips_blur_strip_and_stack(media, tmp_path):
    clips = sanitized(media, [clip(media, "clip", 0, 2), clip(media, "silent", 0, 2)])
    strips = P.sanitize_bgsegs([{"mode": "color", "color": "#ff0000", "start": 1, "dur": 2, "track": 0},
                                {"mode": "color", "color": "#00ff00", "start": 2.5, "dur": 0.5, "track": 1}])
    out = P.render_project(clips, tmp_path / "span", canvas=CANVAS, bg={"mode": "black"}, bgs=strips)
    assert _red(_rgb_at(out, 20, 20, 1.5)) and _red(_rgb_at(out, 20, 20, 2.2))                  # one strip over the clip boundary
    assert _rgb_at(out, 20, 20, 2.75)[1] > 200 and _rgb_at(out, 20, 20, 2.75)[0] < 50           # the higher track lies on top
    assert max(_rgb_at(out, 20, 20, 3.6)) < 20
    blur = P.sanitize_bgsegs([{"mode": "blur", "start": 0.5, "dur": 1}])
    out2 = P.render_project(sanitized(media, [clip(media, "clip", 0, 2)]), tmp_path / "blur", canvas=CANVAS, bg={"mode": "black"}, bgs=blur)
    assert max(mean_rgb(raw_frame(out2, "crop=iw:ih*0.12:0:0", 1.0))) > 40                      # blurred copy of the picture in the strip
    assert max(mean_rgb(raw_frame(out2, "crop=iw:ih*0.12:0:0", 0.2))) < 20


def test_fades_for_text_shape_and_overlay(media, tmp_path):
    clips = sanitized(media, [clip(media, "clip", 0, 4)])
    shape = P.sanitize_shapes([{"kind": "rect", "x": 0.5, "y": 0.5, "w": 1, "h": 1, "color": "#ff0000", "op": 1, "start": 1, "dur": 2, "fi": 1, "fo": 1}])
    out = P.render_project(clips, tmp_path / "shape", shapes=shape)
    assert _rgb_at(out, 600, 330, 1.1) != _rgb_at(out, 600, 330, 2.0) and _red(_rgb_at(out, 600, 330, 2.0))
    assert not _red(_rgb_at(out, 600, 330, 1.1)) and not _red(_rgb_at(out, 600, 330, 2.9))
    txt = P.sanitize_texts([{"text": "HELLO", "start": 1, "dur": 2, "x": 0.5, "y": 0.5, "size": 0.3, "fi": 1, "fo": 1, "color": "#ffffff"}])
    out2 = P.render_project(clips, tmp_path / "txt", texts=txt)
    plain = P.render_project(clips, tmp_path / "txtplain")
    diff = lambda t: sum(abs(a - b) for a, b in zip(_rgb_at(out2, 320, 180, t), _rgb_at(plain, 320, 180, t)))
    assert diff(1.05) < diff(2.0) and diff(2.95) < diff(2.0)


def test_clip_adjustments_change_picture_and_sound(media, tmp_path):
    base = sanitized(media, [clip(media, "clip", 0, 2)])
    plain = P.render_project(base, tmp_path / "a")
    bright = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 2), adj={"br": 0.4, "sa": 0})]), tmp_path / "b")
    p, q = _rgb_at(plain, 320, 180, 1.0), _rgb_at(bright, 320, 180, 1.0)
    assert sum(q) > sum(p) + 30 and abs(q[0] - q[1]) < 25                      # brighter and grey (saturation 0)
    muted = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 2), adj={"mute": True})]), tmp_path / "c")
    import subprocess
    vol = lambda f: float(subprocess.run(["ffmpeg", "-i", str(f), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
                          .split("mean_volume:")[1].split("dB")[0])
    assert vol(muted) < -60 < vol(plain)
    quiet = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 2), adj={"vol": -12})]), tmp_path / "d")
    assert vol(quiet) == pytest.approx(vol(plain) - 12, abs=1.5)
    fade = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 2), adj={"fi": 1, "fo": 1})]), tmp_path / "e")
    assert sum(_rgb_at(fade, 320, 180, 0.05)) < sum(_rgb_at(fade, 320, 180, 1.0)) * 0.5
    assert sum(_rgb_at(fade, 320, 180, 1.95)) < sum(_rgb_at(fade, 320, 180, 1.0)) * 0.5


def test_speed_and_still_frame_change_the_duration(media, tmp_path):
    fast = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 4), sp=2)]), tmp_path / "f")
    slow = P.render_project(sanitized(media, [dict(clip(media, "clip", 0, 1), sp=0.25)]), tmp_path / "s")
    assert ffprobe(fast)["duration"] == pytest.approx(2, abs=0.25) and ffprobe(slow)["duration"] == pytest.approx(4, abs=0.25)
    assert ffprobe(fast)["audio"] and ffprobe(slow)["audio"]
    mixed = sanitized(media, [clip(media, "clip", 0, 1), dict(clip(media, "clip", 1, 1.1), freeze=1.5), clip(media, "clip", 1, 2)])
    out = P.render_project(mixed, tmp_path / "m")
    assert ffprobe(out)["duration"] == pytest.approx(3.5, abs=0.3)
    assert _rgb_at(out, 320, 180, 1.2) == pytest.approx(_rgb_at(out, 320, 180, 2.3), abs=6)    # same frozen picture all along


@pytest.mark.parametrize("kind", ["fade", "slideleft", "circleopen"])
def test_transitions_overlap_clips(media, tmp_path, kind):
    clips = sanitized(media, [clip(media, "clip", 0, 2), dict(clip(media, "silent", 0, 2), tr={"type": kind, "dur": 0.6}),
                              clip(media, "other", 0, 1.5)])
    out = P.render_project(clips, tmp_path / kind)
    assert ffprobe(out)["duration"] == pytest.approx(2 + 2 + 1.5 - 0.6, abs=0.3)
    assert ffprobe(out)["audio"]


def test_transition_after_hard_cuts_and_still_frames(media, tmp_path):
    clips = sanitized(media, [clip(media, "clip", 0, 1), dict(clip(media, "clip", 1, 1.1), freeze=1.5), clip(media, "clip", 1, 2),
                              dict(clip(media, "clip", 2, 4), sp=2, tr={"type": "slideleft", "dur": 0.5}, adj={"br": 0.4})])
    out = P.render_project(clips, tmp_path / "mix")
    assert ffprobe(out)["duration"] == pytest.approx(4.0, abs=0.2) and ffprobe(out)["audio"]


def test_background_strip_uses_clip_start_after_transition(media, tmp_path):
    clips = sanitized(media, [clip(media, "clip", 0, 2), dict(clip(media, "clip", 0, 2), tr={"type": "fade", "dur": 1})])
    strips = P.sanitize_bgsegs([{"mode": "color", "color": "#ff0000", "start": 2.6, "dur": 0.4}])
    out = P.render_project(clips, tmp_path / "t", canvas=CANVAS, bg={"mode": "black"}, bgs=strips)
    assert ffprobe(out)["duration"] == pytest.approx(3, abs=0.3)
    assert _red(_rgb_at(out, 20, 20, 2.8)) and not _red(_rgb_at(out, 20, 20, 2.2))


def test_project_file_roundtrip_keeps_v040_fields():
    proj = {"version": 1, "assets": {"a": {"path": "/x.mp4", "name": "x"}},
            "clips": [{"id": "1", "asset": "a", "in": 0, "out": 2, "adj": {"br": 0.2}, "sp": 2, "tr": {"type": "wipeleft", "dur": 0.4}}],
            "bgs": [{"id": "b1", "mode": "color", "color": "#112233", "start": 1, "dur": 2, "track": 1}],
            "texts": [{"id": "t", "text": "hi", "fi": 1, "fo": 2}]}
    out = P.validate_project(proj)
    assert out["clips"][0]["adj"]["br"] == 0.2 and out["clips"][0]["sp"] == 2 and out["clips"][0]["tr"]["type"] == "wipeleft"
    assert out["bgs"][0]["color"] == "#112233" and out["bgs"][0]["track"] == 1 and out["texts"][0]["fo"] == 2
