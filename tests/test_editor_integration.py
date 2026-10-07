"""Hermes-facing pieces: dashboard API route, Desktop plugin.js (with a stubbed SDK), and a real-browser run."""
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import ROOT, needs_ffmpeg

pytestmark = needs_ffmpeg


# ---------------------------------------------------------------- dashboard/plugin_api.py
def test_manifest_json():
    m = json.loads((ROOT / "dashboard" / "manifest.json").read_text())
    assert m == {"name": "hermes-video-editor", "api": "plugin_api.py"}


def test_plugin_api_start(media):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    import importlib.util
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    spec = importlib.util.spec_from_file_location("ve_plugin_api_under_test", ROOT / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/hermes-video-editor")
    client = TestClient(app)
    r = client.get("/api/plugins/hermes-video-editor/start")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["url"].startswith("http://127.0.0.1:%d/?t=" % data["port"])
    again = client.get("/api/plugins/hermes-video-editor/start").json()
    assert again["url"] == data["url"]                                  # one server per process
    opened = client.get("/api/plugins/hermes-video-editor/start", params={"open": str(media["clip"])}).json()
    assert "open=" in opened["url"]
    assert client.get("/api/plugins/hermes-video-editor/status").json() == {"loaded": True}
    import urllib.request
    with urllib.request.urlopen(data["url"], timeout=10) as resp:        # the URL it hands out really serves the editor
        assert resp.status == 200 and b"Video Editor" in resp.read()


# ---------------------------------------------------------------- desktop/plugin.js
NODE = shutil.which("node")


def run_node(script: str, tmp_path: Path) -> subprocess.CompletedProcess:
    f = tmp_path / "run.mjs"
    f.write_text(script, encoding="utf-8")
    return subprocess.run([NODE, str(f)], capture_output=True, text=True, timeout=60)


def desktop_harness(sdk_js: str, jsx_runtime_js: str, tail: str) -> str:
    """Run desktop/plugin.js against stubbed imports (namespace imports become plain objects)."""
    src = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.startswith("import "))
    body = body.replace("export default", "const plugin_default =")
    return textwrap.dedent("""
        const sdk = %s
        const jsxRuntime = %s
        let hookState = []
        const effects = []
        const React = {
          createElement: (type, props, children) => ({ type, props: Object.assign({}, props, { children }) }),
          useState: init => { const s = [init, v => { s[0] = v }]; hookState.push(s); return s },
          useCallback: fn => fn,
          useEffect: fn => { effects.push(fn) },
        }
        %s
        const regs = []
        const ctx = { registerMany: items => regs.push(...items), calls: [],
                      rest: path => { ctx.calls.push(path); return ctx.reply },
                      reply: Promise.resolve({ url: 'http://127.0.0.1:1/?t=x' }) }
        """) % (sdk_js, jsx_runtime_js, body) + textwrap.dedent(tail)


GOOD_SDK = "{ ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebar-nav', SandboxedFrame: function SandboxedFrame() {} }"
RUNTIME = "{ jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }"


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_desktop_plugin_source_rules():
    src = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    assert "eval(" not in src and "new Function" not in src and "import(" not in src and "data-slot" not in src
    imports = [l for l in src.splitlines() if l.startswith("import ")]
    allowed = ("'@hermes/plugin-sdk'", "'react'", "'react/jsx-runtime'")
    assert imports and all(any(a in l for a in allowed) for l in imports), imports
    assert not any("{ jsx" in l or "jsx," in l for l in imports), "jsx must not be a named import from the SDK"


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_desktop_plugin_registers_page_and_nav(tmp_path):
    script = desktop_harness(GOOD_SDK, RUNTIME, """
        if (plugin_default.id !== 'hermes-video-editor') throw new Error('id must match the plugin folder name')
        plugin_default.register(ctx)
        const page = regs.find(r => r.area === 'routes'), nav = regs.find(r => r.area === 'sidebar-nav')
        if (!page || page.data.path !== '/video-editor') throw new Error('route missing')
        if (!nav || nav.data.path !== page.data.path || !nav.data.label || !nav.data.codicon) throw new Error('nav entry incomplete')
        const tree = page.render()
        const el = tree.type(tree.props)                       // EditorPage, loading state
        if (!JSON.stringify(el).includes('Starting')) throw new Error('loading text missing')
        effects[0]()                                            // useEffect -> load()
        await new Promise(r => setTimeout(r, 20))
        if (ctx.calls[0] !== '/start') throw new Error('did not call /start')
        const [state] = hookState[hookState.length - 1]
        if (state.phase !== 'ready' || !state.url.startsWith('http://127.0.0.1')) throw new Error('not ready: ' + JSON.stringify(state))
        console.log('OK')
        """)
    r = run_node(script, tmp_path)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_desktop_plugin_works_without_jsx_runtime_and_reports_missing_exports(tmp_path):
    # 1) no jsx anywhere -> falls back to React.createElement (this is what failed in the real app)
    ok = desktop_harness(GOOD_SDK, "{}", """
        plugin_default.register(ctx)
        const page = regs.find(r => r.area === 'routes')
        const el = page.render()
        if (!el || !el.type) throw new Error('fallback render failed')
        console.log('OK')
        """)
    r = run_node(ok, tmp_path)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout
    # 2) missing SDK exports -> a clear error naming them and listing what exists
    bad = desktop_harness("{ jsx: () => null, Codicon: 1 }", RUNTIME, """
        try { plugin_default.register(ctx); throw new Error('should have thrown') }
        catch (e) { console.log(e.message) }
        """)
    r = run_node(bad, tmp_path)
    assert "ROUTES_AREA, SIDEBAR_NAV_AREA, SandboxedFrame" in r.stdout and "jsx, Codicon" in r.stdout, r.stdout + r.stderr


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_app_js_syntax():
    r = subprocess.run([NODE, "--check", str(ROOT / "editor" / "web" / "app.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    js = (ROOT / "editor" / "web" / "app.js").read_text()
    assert "eval(" not in js and "document.write" not in js


def test_no_inline_script_or_remote_assets_in_html():
    html = (ROOT / "editor" / "web" / "index.html").read_text()
    assert "<script>" not in html and "http://" not in html and "https://" not in html


# ---------------------------------------------------------------- real browser (optional)
def test_browser_end_to_end(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                pytest.skip("no usable chromium: %s" % exc)
            page = browser.new_page(viewport={"width": 1500, "height": 880})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.url(str(media["gap"])))
            page.wait_for_selector("#overlay[hidden]", state="attached", timeout=90000)
            page.wait_for_timeout(1500)
            assert "gap.mp4" in page.inner_text("#file-chip")
            page.click("#btn-silence")
            page.wait_for_selector("#cuts-list .item", timeout=20000)
            assert page.inner_text("#cut-count") == "1"
            assert "Keeps" in page.inner_text("#summary")
            # manual cut with the keyboard: mark 0.2 -> 0.6 and press X
            page.evaluate("document.getElementById('video').currentTime = 0.2")
            page.keyboard.press("i")
            page.evaluate("document.getElementById('video').currentTime = 0.6")
            page.keyboard.press("o")
            page.keyboard.press("x")
            assert page.inner_text("#cut-count") == "2"
            page.click('#cuts-list .item >> nth=0 >> button[title="Remove this cut"]')   # remove the silence cut
            assert page.inner_text("#cut-count") == "1"
            page.click("#tabs button[data-tab=picture]")
            page.select_option("#in-reframe", "crop_1x1")
            assert page.is_visible("#frame-guide")
            page.click("#tabs button[data-tab=export]")
            page.select_option("#in-preset", "web_mp4")
            page.fill("#in-outdir", str(tmp_path / "ui-out"))
            page.click("#btn-export")
            page.wait_for_selector("#result .ok", timeout=120000)
            out = list((tmp_path / "ui-out").glob("*.mp4"))
            assert len(out) == 1
            assert not errors, errors
            browser.close()
    finally:
        srv.stop()
