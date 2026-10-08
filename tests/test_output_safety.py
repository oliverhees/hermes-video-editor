"""Review fixes: a tool only ever creates its own files. Outputs have media/picture/.srt suffixes, results are built in a
temporary file and moved into place on success, and a failure never deletes or damages an existing file."""
import sys
import types
from pathlib import Path

import pytest

from conftest import call, ffprobe, needs_ffmpeg, sha
from hermes_video_editor.core import ffmpeg as ff_mod
from hermes_video_editor.core.paths import ALLOWED_OUTPUT_EXTS, plan_output
from hermes_video_editor.core.result import ToolError

pytestmark = needs_ffmpeg


def leftovers(folder):
    return sorted(p.name for p in Path(folder).iterdir() if ".part" in p.name)


# ------------------------------------------------------------------ 1. suffix policy
def test_output_suffix_must_be_media_picture_or_srt(media, tmp_path):
    src = media["clip"]
    for bad in ("evil.sh", "evil.py", "evil.json", "evil.desktop", "evil.txt"):
        r = call("lk_trim", input=str(src), start=0, duration=1, output=str(tmp_path / bad))
        assert r["ok"] is False and "suffix" in r["error"], bad
        assert not (tmp_path / bad).exists()
    assert list(tmp_path.iterdir()) == []
    ok = call("lk_trim", input=str(src), start=0, duration=1, output=str(tmp_path / "fine.MKV"))        # case does not matter
    assert ok["ok"] and Path(ok["output"]).suffix == ".MKV"
    dotfile = call("lk_trim", input=str(src), start=0, duration=1, output=str(tmp_path / ".bashrc"))     # no suffix: gets the media one
    assert dotfile["ok"] and dotfile["output"].endswith(".bashrc.mp4")
    folder = tmp_path / "some.mp4"
    folder.mkdir()
    assert call("lk_trim", input=str(src), start=0, duration=1, output=str(folder))["ok"] is False        # an existing folder is not a file


def test_plan_output_rules(media, tmp_path):
    src = media["clip"]
    assert plan_output(src, "x", ".mp4", str(tmp_path / "a.mp3")).suffix == ".mp3"
    assert plan_output(src, "x", ".srt", str(tmp_path / "a.srt"), strict_ext=True).suffix == ".srt"
    with pytest.raises(ToolError):
        plan_output(src, "x", ".srt", str(tmp_path / "a.mp4"), strict_ext=True)       # a captions tool writes .srt only
    with pytest.raises(ToolError):
        plan_output(src, "x", ".mp4", str(tmp_path / "a.exe"))
    assert {".mp4", ".mp3", ".png", ".gif", ".srt"} <= ALLOWED_OUTPUT_EXTS and ".sh" not in ALLOWED_OUTPUT_EXTS and ".py" not in ALLOWED_OUTPUT_EXTS


def test_captions_tool_only_writes_srt(media, tmp_path, monkeypatch):
    class Seg:
        def __init__(self, a, b, t):
            self.start, self.end, self.text = a, b, t

    class Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            return iter([Seg(0, 1, "Hello"), Seg(1, 2, "World")]), types.SimpleNamespace(language="en")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    r = call("lk_transcribe_captions", input=str(media["clip"]), output=str(tmp_path / "a.mp4"))
    assert r["ok"] is False and ".srt" in r["error"] and not (tmp_path / "a.mp4").exists()
    r = call("lk_transcribe_captions", input=str(media["clip"]), output=str(tmp_path / "ok.srt"))
    assert r["ok"] and "Hello" in (tmp_path / "ok.srt").read_text() and leftovers(tmp_path) == []
    # an existing .srt is kept unless overwrite is asked for
    (tmp_path / "keep.srt").write_text("MINE")
    again = call("lk_transcribe_captions", input=str(media["clip"]), output=str(tmp_path / "keep.srt"))
    assert again["ok"] and (tmp_path / "keep.srt").read_text() == "MINE" and again["output"].endswith("keep_1.srt")


# ------------------------------------------------------------------ 2. never delete or damage a file the tool did not create
def failing_ffmpeg(monkeypatch, fail_on=1):
    """run_ffmpeg that writes a partial output to the last argument, then fails (like a crash half way through)."""
    state = {"n": 0}
    real = ff_mod.run_ffmpeg

    def fake(args, timeout, loglevel="error"):
        if args[-1] == "-":
            return real(args, timeout, loglevel)
        state["n"] += 1
        Path(args[-1]).write_bytes(b"PARTIAL" * 100)
        if state["n"] >= fail_on:
            raise ToolError("ffmpeg crashed")
        return types.SimpleNamespace(stderr="", stdout="")
    monkeypatch.setattr(ff_mod, "run_ffmpeg", fake)
    return state


def test_failed_run_leaves_an_existing_output_untouched(media, tmp_path, monkeypatch):
    victim = tmp_path / "important.mp4"
    victim.write_bytes(b"MY PRECIOUS FILE")
    before = sha(victim)
    failing_ffmpeg(monkeypatch)
    r = call("lk_trim", input=str(media["clip"]), start=0, duration=1, output=str(victim), overwrite=True)
    assert r["ok"] is False
    assert sha(victim) == before and leftovers(tmp_path) == []              # not deleted, not damaged, no temp file left behind


def test_success_replaces_atomically_with_overwrite_and_keeps_files_without(media, tmp_path):
    target = tmp_path / "result.mp4"
    target.write_bytes(b"OLD")
    r = call("lk_trim", input=str(media["clip"]), start=0, duration=1, output=str(target))              # no overwrite: new name
    assert r["ok"] and r["output"].endswith("result_1.mp4") and target.read_bytes() == b"OLD"
    r = call("lk_trim", input=str(media["clip"]), start=0, duration=1, output=str(target), overwrite=True)
    assert r["ok"] and r["output"] == str(target) and ffprobe(target)["duration"] == pytest.approx(1, abs=0.2)
    assert leftovers(tmp_path) == []


def test_split_failure_leaves_no_parts_and_keeps_existing_files(media, tmp_path, monkeypatch):
    out = tmp_path / "parts"
    out.mkdir()
    existing = out / (Path(media["clip"]).stem + "_part1.mp4")
    existing.write_bytes(b"EXISTING PART")
    failing_ffmpeg(monkeypatch, fail_on=2)                                  # second part crashes
    r = call("lk_split", input=str(media["clip"]), times=[1, 2], output_dir=str(out), overwrite=True)
    assert r["ok"] is False
    assert existing.read_bytes() == b"EXISTING PART" and sorted(p.name for p in out.iterdir()) == [existing.name]


def test_compress_failure_keeps_an_existing_file(media, tmp_path, monkeypatch):
    victim = tmp_path / "small.mp4"
    victim.write_bytes(b"KEEP ME")
    real = ff_mod.run_ffmpeg

    def huge(args, timeout, loglevel="error"):                              # every attempt "produces" a file far above the target
        if args[-1] == "-":
            return types.SimpleNamespace(stderr="", stdout="")
        Path(args[-1]).write_bytes(b"x" * 3_000_000)
        return types.SimpleNamespace(stderr="", stdout="")
    monkeypatch.setattr(ff_mod, "run_ffmpeg", huge)
    import hermes_video_editor.tools.export as export_mod
    monkeypatch.setattr(export_mod, "run_ffmpeg", huge)
    r = call("lk_compress_to_size", input=str(media["noisy"]), target_mb=1, output=str(victim), overwrite=True)
    assert r["ok"] is False and "Could not reach" in r["error"]
    assert victim.read_bytes() == b"KEEP ME" and leftovers(tmp_path) == []
    monkeypatch.setattr(ff_mod, "run_ffmpeg", real)


def test_editor_render_uses_a_temporary_file(media, tmp_path, monkeypatch):
    from hermes_video_editor.editor import project as P
    clips = P.sanitize_clips([{"path": str(media["clip"]), "in": 0, "out": 1}], [str(media["dir"])])
    existing = tmp_path / (Path(media["clip"]).stem + "_project.mp4")
    existing.write_bytes(b"MINE")
    out = P.render_project(clips, tmp_path)
    assert out != existing and existing.read_bytes() == b"MINE" and leftovers(tmp_path) == []        # next free name, original kept

    def boom(args, timeout, loglevel="error"):
        Path(args[-1]).write_bytes(b"PARTIAL")
        raise ToolError("crash")
    monkeypatch.setattr(P, "run_ffmpeg", boom)
    with pytest.raises(ToolError):
        P.render_project(clips, tmp_path / "second")
    assert leftovers(tmp_path / "second") == [] and list((tmp_path / "second").iterdir()) == []
