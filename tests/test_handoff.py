"""lk_open_in_editor: the agent hands a video to the editor through a small queue; the editor picks it up."""
import json
import urllib.request

import pytest

from conftest import ROOT, call, needs_ffmpeg
from hermes_video_editor.editor import handoff
from test_editor_integration import browser, state, wait_ready

pytestmark = needs_ffmpeg


@pytest.fixture(autouse=True)
def private_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("VE_QUEUE_DIR", str(tmp_path / "q"))


def test_tool_queues_a_video_and_a_project_and_checks_the_file(media, tmp_path):
    r = call("lk_open_in_editor", input=str(media["clip"]))
    assert r["ok"] and r["info"]["queued"] and r["info"]["kind"] == "media" and "Video Editor" in r["info"]["how_to_open"]
    call("lk_open_in_editor", input=str(media["clip"]))                          # the same file twice is one request
    proj = tmp_path / "x.vproj.json"
    proj.write_text("{}")
    assert call("lk_open_in_editor", input=str(proj), focus=False)["info"]["kind"] == "project"
    items = handoff.pop_all()
    assert [i["kind"] for i in items] == ["media", "project"] and items[1]["focus"] is False and items[0]["name"] == "clip.mp4"
    assert handoff.pop_all() == []                                               # asking empties the queue
    assert call("lk_open_in_editor", input=str(tmp_path / "missing.mp4"))["ok"] is False
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert call("lk_open_in_editor", input=str(junk))["ok"] is False
    assert handoff.pop_all() == []


def test_old_requests_expire(media, monkeypatch):
    call("lk_open_in_editor", input=str(media["clip"]))
    monkeypatch.setattr(handoff.time, "time", lambda: 10 ** 10)
    assert handoff.pop_all() == []


def test_editor_server_and_plugin_route_hand_the_queue_out(media, tmp_path):
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(tmp_path)])
    try:
        call("lk_open_in_editor", input=str(media["clip"]))
        url = srv.url().split("?")[0] + "api/pending?t=" + srv.token
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        assert data["ok"] and data["items"][0]["path"] == str(media["clip"])
        assert any(str(media["dir"]) == r or str(media["dir"]).startswith(r) for r in srv.roots)      # its folder is open for the editor now
        with urllib.request.urlopen(url, timeout=10) as resp:
            assert json.loads(resp.read())["items"] == []
    finally:
        srv.stop()


def test_dashboard_route_pending(media):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import importlib.util
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    spec = importlib.util.spec_from_file_location("ve_plugin_api_pending", ROOT / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/hermes-video-editor")
    client = TestClient(app)
    base = "/api/plugins/hermes-video-editor"
    assert client.get(base + "/pending").json() == {"items": []}
    call("lk_open_in_editor", input=str(media["clip"]))
    items = client.get(base + "/pending").json()["items"]
    assert len(items) == 1 and items[0]["path"] == str(media["clip"])


def test_standalone_editor_loads_an_empty_timeline_and_asks_before_adding_to_work(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        call("lk_open_in_editor", input=str(media["clip"]))
        page.goto(srv.url())
        wait_ready(page)                                                         # the empty editor loads the handed-over video by itself
        assert state(page, "s.clips.length") == 1
        call("lk_open_in_editor", input=str(media["silent"]))                    # now there is work on the timeline: a note, not a surprise
        page.wait_for_selector("#handover:not([hidden])", timeout=15000)
        assert "silent.mp4" in page.inner_text("#handover") and state(page, "s.clips.length") == 1
        page.click("#handover .btn.primary")
        for _ in range(100):
            if state(page, "s.clips.length") == 2:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.clips.length") == 2 and not errors, errors
    finally:
        b.close(); p.stop(); srv.stop()
