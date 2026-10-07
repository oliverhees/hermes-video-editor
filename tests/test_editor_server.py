"""Editor server: auth, path policy, streaming, jobs and the export pipeline (real ffmpeg, real HTTP)."""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from conftest import ffprobe, needs_ffmpeg
from hermes_video_editor.editor import jobs as jobs_mod
from hermes_video_editor.editor.security import inside, safe_dir, safe_media_file
from hermes_video_editor.editor.server import EditorServer, parse_range
from hermes_video_editor.core.result import ToolError

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def srv(media):
    server = EditorServer(roots=[str(media["dir"])])
    yield server
    server.stop()


class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def req(srv, route, params=None, body=None, token=True, headers=None):
    q = dict(params or {})
    if token:
        q["t"] = srv.token
    url = "http://127.0.0.1:%d%s?%s" % (srv.port, route, urllib.parse.urlencode(q))
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=dict(headers or {}, **({"Content-Type": "application/json"} if data else {})))
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return Resp(resp.status, resp.headers, resp.read())
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.headers, e.read())


def wait_job(srv, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = req(srv, "/api/job", {"id": job_id}).json()
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    raise AssertionError("job timed out")


# ---------------------------------------------------------------- auth
def test_token_required(srv, media):
    assert req(srv, "/api/config", token=False).status == 403
    assert req(srv, "/api/config", {"t": "wrong"}, token=False).status == 403
    assert req(srv, "/api/ls", {"path": str(media["dir"])}, token=False).status == 403
    assert req(srv, "/api/config").status == 200


def test_host_header_checked(srv):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.request("GET", "/api/config?t=" + srv.token, headers={"Host": "evil.example:%d" % srv.port})
    assert c.getresponse().status == 403
    c.close()


def test_static_and_index(srv):
    r = req(srv, "/static/app.js", token=False)
    assert r.status == 200 and "javascript" in r.headers["Content-Type"]
    assert req(srv, "/static/secret.txt", token=False).status == 404
    assert req(srv, "/static/../server.py", token=False).status == 404                   # nothing but app.js/app.css
    assert req(srv, "/static/app.css").status == 200
    idx = req(srv, "/")
    assert idx.status == 200 and b"Video Editor" in idx.body
    assert "script-src 'self'" in idx.headers["Content-Security-Policy"]
    assert req(srv, "/").headers["Access-Control-Allow-Origin"] == "*"   # needed: the sandboxed frame has an opaque origin


def test_listens_on_loopback_only(srv):
    assert srv.httpd.server_address[0] == "127.0.0.1"


def test_invalid_post_bodies(srv):
    r = urllib.request.Request("http://127.0.0.1:%d/api/export?t=%s" % (srv.port, srv.token), data=b"not json", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(r)
    assert e.value.code == 400
    assert req(srv, "/api/export", body=[1, 2]).status == 400
    assert req(srv, "/api/nope").status == 404


# ---------------------------------------------------------------- path policy
def test_ls_and_roots(srv, media):
    d = req(srv, "/api/ls", {"path": str(media["dir"])}).json()
    names = {f["name"] for f in d["files"]}
    assert {"clip.mp4", "silent.mp4"} <= names and "mein Ordner ünï" in {x["name"] for x in d["dirs"]}
    assert req(srv, "/api/ls", {"path": "/"}).status == 400
    assert req(srv, "/api/ls", {"path": str(media["dir"] / ".." / "..")}).status == 400


def test_media_policy(srv, media, tmp_path):
    txt = media["dir"] / "notes.txt"
    txt.write_text("secret")
    assert req(srv, "/api/media", {"path": str(txt)}).status == 400                    # not a media type
    assert req(srv, "/api/media", {"path": "/etc/passwd"}).status == 400               # outside roots
    link = media["dir"] / "leak.mp4"
    try:
        if not link.exists():
            os.symlink(os.path.realpath(__file__), str(link))                          # points outside the root
        assert req(srv, "/api/media", {"path": str(link)}).status == 400               # symlink escaping the root
    except OSError:
        pass                                                                           # Windows without symlink rights
    assert req(srv, "/api/probe", {"path": str(media["dir"] / "missing.mp4")}).status == 400
    assert req(srv, "/api/cache", {"id": "../../etc", "name": "proxy.mp4"}).status == 400
    assert req(srv, "/api/cache", {"id": "0123456789abcdef", "name": "../x"}).status == 400


def test_security_helpers(tmp_path):
    root = str(tmp_path)
    assert inside(str(tmp_path / "a" / "b.mp4"), [root]) and not inside(str(tmp_path.parent), [root])
    assert not inside(str(tmp_path) + "-evil/x.mp4", [root])                             # prefix is not containment
    (tmp_path / "v.mp4").write_bytes(b"x")
    assert safe_media_file(str(tmp_path / "v.mp4"), [root]).name == "v.mp4"
    for bad in (None, "", 5, str(tmp_path / "nope.mp4"), str(tmp_path / "v.exe")):
        with pytest.raises(ToolError):
            safe_media_file(bad, [root])
    with pytest.raises(ToolError):
        safe_dir("/", [root])


# ---------------------------------------------------------------- streaming
def test_media_full_and_range(srv, media):
    size = os.path.getsize(media["clip"])
    full = req(srv, "/api/media", {"path": str(media["clip"])})
    assert full.status == 200 and len(full.body) == size and full.headers["Accept-Ranges"] == "bytes"
    part = req(srv, "/api/media", {"path": str(media["clip"])}, headers={"Range": "bytes=10-109"})
    assert part.status == 206 and len(part.body) == 100 and part.body == full.body[10:110]
    assert part.headers["Content-Range"] == "bytes 10-109/%d" % size
    tail = req(srv, "/api/media", {"path": str(media["clip"])}, headers={"Range": "bytes=-50"})
    assert tail.status == 206 and tail.body == full.body[-50:]
    assert req(srv, "/api/media", {"path": str(media["clip"])}, headers={"Range": "bytes=%d-" % (size + 5)}).status == 416
    assert req(srv, "/api/media", {"path": str(media["tricky"])}).status == 200          # unicode + spaces


def test_parse_range():
    assert parse_range(None, 100) is None and parse_range("items=1-2", 100) is None
    assert parse_range("bytes=0-9", 100) == (0, 9)
    assert parse_range("bytes=90-", 100) == (90, 99)
    assert parse_range("bytes=-10", 100) == (90, 99)
    assert parse_range("bytes=50-500", 100) == (50, 99)
    assert parse_range("bytes=x-y", 100) is None
    with pytest.raises(ValueError):
        parse_range("bytes=100-", 100)


# ---------------------------------------------------------------- prepare / probe / silence
def test_probe_endpoint(srv, media):
    info = req(srv, "/api/probe", {"path": str(media["clip"])}).json()
    assert info["video"]["width"] == 640 and info["has_audio"]


def test_playback_plan(media):
    from hermes_video_editor.core.ffmpeg import probe
    info = probe(media["clip"])
    assert jobs_mod.playback_plan(media["clip"], info, True) == "original"
    assert jobs_mod.playback_plan(media["clip"], info, False) == "vp8"                  # browser without H.264
    assert jobs_mod.playback_plan(media["rotated"], probe(media["rotated"]), True) == "h264"
    assert jobs_mod.playback_plan(media["odd"], probe(media["odd"]), True) == "h264"    # yuv444p: not browser safe


def test_prepare_original(srv, media):
    job = req(srv, "/api/prepare", body={"path": str(media["clip"]), "h264": True}).json()["job"]
    j = wait_job(srv, job)
    assert j["state"] == "done", j
    r = j["result"]
    assert r["playback"] == {"kind": "original"} and r["has_waveform"] and r["thumbs"]["count"] >= 8
    cid = r["cache_id"]
    wave = req(srv, "/api/waveform", {"id": cid}).json()
    assert len(wave) >= 200 and 0 <= min(wave) and max(wave) == 1.0
    thumbs = req(srv, "/api/cache", {"id": cid, "name": "thumbs.jpg"})
    assert thumbs.status == 200 and thumbs.body[:2] == b"\xff\xd8"


def test_prepare_proxy_for_browser_without_h264(srv, media):
    if not jobs_mod.has_encoder("libvpx"):
        pytest.skip("ffmpeg build without libvpx")
    job = req(srv, "/api/prepare", body={"path": str(media["clip"]), "h264": False}).json()["job"]
    j = wait_job(srv, job)
    assert j["state"] == "done", j
    pb = j["result"]["playback"]
    assert pb == {"kind": "proxy", "name": "proxy.webm"}
    proxy = req(srv, "/api/cache", {"id": j["result"]["cache_id"], "name": "proxy.webm"})
    assert proxy.status == 200 and proxy.body[:4] == b"\x1a\x45\xdf\xa3"                # EBML header


def test_prepare_silent_clip_has_no_waveform(srv, media):
    j = wait_job(srv, req(srv, "/api/prepare", body={"path": str(media["silent"])}).json()["job"])
    assert j["state"] == "done" and not j["result"]["has_waveform"] and j["result"]["thumbs"]


def test_silence_endpoint(srv, media):
    r = req(srv, "/api/silence", body={"path": str(media["gap"]), "noise_db": -35, "min_silence_s": 0.5}).json()
    assert r["count"] == 1 and r["silences"][0]["start_s"] == pytest.approx(1.0, abs=0.2)
    assert req(srv, "/api/silence", body={"path": str(media["silent"])}).status == 400   # no audio
    assert req(srv, "/api/silence", body={"path": str(media["gap"]), "noise_db": 10}).status == 400


# ---------------------------------------------------------------- export
def test_build_steps_pure():
    steps = jobs_mod.build_steps({"cuts": [[1, 2]], "speed": 1.5, "reframe": "crop_9x16", "anchor": "left",
                                  "loudness": -14, "preset": "reels"})
    assert [s["tool"] for s in steps] == ["lk_remove_segments", "lk_change_speed", "lk_crop_to_aspect",
                                         "lk_normalize_loudness", "lk_export_preset"]
    assert steps[2]["args"] == {"aspect": "9:16", "anchor": "left"}
    assert steps[0]["args"]["segments"] == [{"start": 1.0, "end": 2.0}]
    assert jobs_mod.build_steps({}) == []
    assert jobs_mod.build_steps({"reframe": "blur_9x16"})[0]["tool"] == "lk_pad_blur_background"


def test_export_pipeline(srv, media, tmp_path):
    out = tmp_path / "exports"
    out.mkdir()
    srv.add_root(str(tmp_path))
    before = os.path.getsize(media["gap"])
    body = {"path": str(media["gap"]), "cuts": [[1.0, 2.5]], "speed": 1.0, "reframe": "crop_1x1", "loudness": -16,
            "preset": "web_mp4", "output_dir": str(out)}
    j = wait_job(srv, req(srv, "/api/export", body=body).json()["job"])
    assert j["state"] == "done", j
    res = j["result"]
    assert res["output"].startswith(str(out)) and os.path.isfile(res["output"])
    p = ffprobe(res["output"])
    assert p["duration"] == pytest.approx(2.5, abs=0.4)
    assert p["video"]["width"] == p["video"]["height"] == 240                            # 320x240 -> 1:1 crop
    assert res["steps"][0] == "Removing cuts" and res["platform_check"] is not None
    assert os.path.getsize(media["gap"]) == before
    assert sorted(os.listdir(str(out))) == [os.path.basename(res["output"])]            # temp files cleaned up


def test_export_without_preset_lands_next_to_input(srv, media):
    j = wait_job(srv, req(srv, "/api/export", body={"path": str(media["silent"]), "speed": 2.0}).json()["job"])
    assert j["state"] == "done", j
    assert os.path.dirname(j["result"]["output"]) == str(media["dir"]) and j["result"]["platform_check"] is None


@pytest.mark.parametrize("body", [
    {"cuts": [[2, 1]]}, {"cuts": [[-1, 2]]}, {"cuts": ["x"]}, {"speed": 3}, {"reframe": "weird"}, {"preset": "myspace"},
    {"loudness": 5}, {"output_dir": "/etc"},
])
def test_export_validation(srv, media, body):
    r = req(srv, "/api/export", body=dict({"path": str(media["clip"])}, **body))
    assert r.status == 400 and r.json()["ok"] is False


def test_export_nothing_to_do_and_job_errors(srv, media):
    j = wait_job(srv, req(srv, "/api/export", body={"path": str(media["clip"])}).json()["job"])
    assert j["state"] == "error" and "Nothing to export" in j["error"]["error"]
    j = wait_job(srv, req(srv, "/api/export", body={"path": str(media["silent"]), "loudness": -14}).json()["job"])
    assert j["state"] == "error"                                                          # silent clip has no audio to normalise
    assert req(srv, "/api/job", {"id": "nope"}).status == 404


# ---------------------------------------------------------------- recent files and uploads
def post_raw(srv, route, params, data, headers=None):
    q = dict(params, t=srv.token)
    r = urllib.request.Request("http://127.0.0.1:%d%s?%s" % (srv.port, route, urllib.parse.urlencode(q)), data=data,
                               headers=dict({"Content-Type": "application/octet-stream"}, **(headers or {})), method="POST")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return Resp(resp.status, resp.headers, resp.read())
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.headers, e.read())


def test_recent_files(srv, media):
    wait_job(srv, req(srv, "/api/prepare", body={"path": str(media["silent"])}).json()["job"])
    files = req(srv, "/api/recent").json()["files"]
    assert files and files[0]["path"] == str(media["silent"]) and files[0]["name"] == "silent.mp4"
    assert req(srv, "/api/recent", token=False).status == 403


def test_upload_drop(srv, media):
    data = open(media["silent"], "rb").read()
    r = post_raw(srv, "/api/upload", {"name": "my dropped clip.mp4"}, data)
    assert r.status == 200, r.body
    path = r.json()["path"]
    assert os.path.basename(path) == "my dropped clip.mp4" and open(path, "rb").read() == data
    assert req(srv, "/api/probe", {"path": path}).json()["has_video"]            # inside the allowed upload folder
    again = post_raw(srv, "/api/upload", {"name": "my dropped clip.mp4"}, data).json()["path"]
    assert again != path and again.endswith("my dropped clip_1.mp4")              # never overwrites
    evil = post_raw(srv, "/api/upload", {"name": "../../etc/evil.mp4"}, data).json()["path"]
    assert os.path.dirname(evil) == os.path.dirname(path)                          # path components stripped
    for p in (path, again, evil):
        os.unlink(p)


def test_upload_rejects_bad_requests(srv, media):
    assert post_raw(srv, "/api/upload", {"name": "script.exe"}, b"MZ").status == 400
    assert post_raw(srv, "/api/upload", {"name": "x.mp4"}, b"").status == 400
    assert post_raw(srv, "/api/upload", {}, b"abc").status == 400
    r = urllib.request.Request("http://127.0.0.1:%d/api/upload?name=x.mp4" % srv.port, data=b"abc", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(r)
    assert e.value.code == 403                                                     # no token
    assert not [n for n in os.listdir(str(jobs_mod.UPLOAD_DIR)) if n.endswith(".part")]


def test_config_has_videos_dir(srv):
    cfg = req(srv, "/api/config").json()
    assert os.path.isdir(cfg["videos_dir"]) and str(jobs_mod.UPLOAD_DIR) in cfg["roots"]


# ---------------------------------------------------------------- all tools through the editor API
def test_tool_catalog_lists_all_tools(srv):
    r = req(srv, "/api/tools").json()
    names = [t["name"] for t in r["tools"]]
    assert len(names) == 45 and len(set(names)) == 45
    assert r["groups"] == ["Inspect", "Cut & time", "Picture", "Overlays & text", "Audio", "Export & check"]
    assert {t["group"] for t in r["tools"]} == set(r["groups"])
    assert {t["name"] for t in r["tools"] if t["read_only"]} == {
        "lk_media_doctor", "lk_media_probe", "lk_detect_silence", "lk_detect_scenes", "lk_platform_check", "lk_loudness_report"}
    trim = next(t for t in r["tools"] if t["name"] == "lk_trim")
    assert "start" in trim["properties"] and "input" in trim["properties"]


def run_tool_api(srv, name, args, expect_ok=True):
    r = req(srv, "/api/tool", body={"name": name, "args": args})
    if r.status != 200:
        return r
    j = wait_job(srv, r.json()["job"])
    assert (j["state"] == "done") == expect_ok, j
    return j


def test_run_tools_from_editor(srv, media, tmp_path):
    srv.add_root(str(tmp_path))
    out = tmp_path / "tool-out"
    j = run_tool_api(srv, "lk_trim", {"input": str(media["clip"]), "start": 1, "duration": 1, "output_dir": str(out)})
    assert os.path.isfile(j["result"]["output"]) and j["result"]["output"].startswith(str(out))
    j = run_tool_api(srv, "lk_media_probe", {"input": str(media["clip"])})
    assert j["result"]["info"]["video"]["width"] == 640
    j = run_tool_api(srv, "lk_split", {"input": str(media["clip"]), "times": [1, 2], "output_dir": str(out)})
    assert len(j["result"]["info"]["outputs"]) == 3
    j = run_tool_api(srv, "lk_join", {"inputs": [str(media["clip"]), str(media["clip"])], "output_dir": str(out)})
    assert j["result"]["info"]["method"] == "stream_copy"
    j = run_tool_api(srv, "lk_remove_segments", {"input": str(media["clip"]), "output_dir": str(out),
                                                 "segments": [{"start": "0:01", "end": "0:02"}]})
    assert j["result"]["ok"]
    j = run_tool_api(srv, "lk_media_doctor", {})
    assert j["result"]["info"]["encoders"]["libx264"]
    bad = run_tool_api(srv, "lk_trim", {"input": str(media["clip"]), "start": "abc", "output_dir": str(out)}, expect_ok=False)
    assert "Invalid start" in bad["error"]["error"]


def test_tool_api_confines_paths_and_parameters(srv, media, tmp_path):
    base = {"input": str(media["clip"])}
    assert run_tool_api(srv, "ve_nope", base).status == 400
    assert run_tool_api(srv, "lk_trim", dict(base, evil="1")).status == 400                 # not a schema parameter
    assert run_tool_api(srv, "lk_trim", {"input": "/etc/passwd"}).status == 400
    assert run_tool_api(srv, "lk_trim", dict(base, output_dir="/etc")).status == 400
    assert run_tool_api(srv, "lk_trim", dict(base, output="/etc/cron.d/x.mp4")).status == 400
    assert run_tool_api(srv, "lk_trim", dict(base, output=str(tmp_path / "x.sh"))).status == 400
    assert run_tool_api(srv, "lk_join", {"inputs": ["/etc/passwd", str(media["clip"])]}).status == 400
    assert run_tool_api(srv, "lk_burn_captions", dict(base, captions="/etc/passwd")).status == 400
    assert run_tool_api(srv, "lk_add_text", dict(base, text="x", font_file=str(media["clip"]))).status == 400
    assert run_tool_api(srv, "lk_trim", "not a dict").status == 400
    assert req(srv, "/api/tool", body={"name": "lk_trim", "args": base}, token=False).status == 403


def test_tool_results_for_uploaded_files_go_to_videos_folder(srv, media):
    data = open(media["silent"], "rb").read()
    uploaded = post_raw(srv, "/api/upload", {"name": "tooltest.mp4"}, data).json()["path"]
    videos = req(srv, "/api/config").json()["videos_dir"]
    j = run_tool_api(srv, "lk_trim", {"input": uploaded, "duration": 1})
    try:
        assert os.path.dirname(j["result"]["output"]) == videos
    finally:
        os.unlink(uploaded)
        os.unlink(j["result"]["output"])


def test_ls_kinds(srv, media):
    (media["dir"] / "caps.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
    (media["dir"] / "logo.png").write_bytes(b"\x89PNG")
    names = lambda kind: {f["name"] for f in req(srv, "/api/ls", {"path": str(media["dir"]), "kind": kind}).json()["files"]}  # noqa: E731
    assert "caps.srt" in names("captions") and "clip.mp4" not in names("captions")
    assert "logo.png" in names("image") and "clip.mp4" in names("image")
    assert "clip.mp4" in names("media") and "logo.png" not in names("media")
