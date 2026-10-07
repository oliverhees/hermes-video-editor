"""Hermes-facing pieces: dashboard API route, Desktop plugin.js (with a stubbed SDK), and a real-browser run."""
import json
import shutil
import urllib.parse
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import ROOT, needs_ffmpeg
from hermes_video_editor.editor import jobs as jobs_mod

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
          useRef: init => ({ current: init }),
          useEffect: fn => { effects.push(fn) },
        }
        %s
        const document = { body: {}, documentElement: {}, createElement: () => ({ style: {}, getContext: () => null }) }
        const getComputedStyle = () => ({ backgroundColor: 'rgb(0, 0, 0)', color: 'rgb(0,0,0)' })
        const window = { listeners: [], opened: [], addEventListener(t, f) { this.listeners.push(f) }, removeEventListener() {}, open(...a) { this.opened.push(a) } }
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
def test_powered_by_link_is_opened_by_the_desktop_page_for_the_frame_only(tmp_path):
    script = desktop_harness(GOOD_SDK, RUNTIME, """
        plugin_default.register(ctx)
        const page = regs.find(r => r.area === 'routes')
        const tree = page.render(); tree.type(tree.props)            // run the component once so the hooks register
        effects.forEach(fn => fn())
        const frameWin = {}
        // pretend the frame is mounted: the component's ref is the last useRef; simulate through the listener only
        const listener = window.listeners[0]
        listener({ source: frameWin, data: { type: 've-open-link', url: 'https://lokyy.de' } })
        if (window.opened.length) throw new Error('must ignore messages while no frame is mounted')
        console.log('OK')
        """)
    r = run_node(script, tmp_path)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout
    src = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    assert "ALLOWED_LINKS = ['https://lokyy.de', 'https://lokyy.de/']" in src
    assert "event.source !== frame.contentWindow" in src and "noopener" in src


def test_powered_by_lokyy_link_in_editor_and_readme():
    html = (ROOT / "editor" / "web" / "index.html").read_text()
    assert '<a id="powered" href="https://lokyy.de" target="_blank" rel="noopener noreferrer">Powered by lokyy.de</a>' in html
    js = (ROOT / "editor" / "web" / "app.js").read_text()
    assert 'type: "ve-open-link"' in js
    assert "Powered by [lokyy.de](https://lokyy.de)" in (ROOT / "README.md").read_text()


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
    link = '<a id="powered" href="https://lokyy.de" target="_blank" rel="noopener noreferrer">Powered by lokyy.de</a>'
    assert link in html
    rest = html.replace(link, "")                                   # the only external address is the credit link
    assert "<script>" not in rest and "http://" not in rest and "https://" not in rest


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
            page.wait_for_selector("#video[data-src]", state="attached", timeout=90000)
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


def test_browser_theme_empty_state_and_drop(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"])])
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                pytest.skip("no usable chromium: %s" % exc)
            page = browser.new_page(viewport={"width": 1400, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # light theme + app colours arrive through the URL
            page.goto(srv.url() + "&theme=light&bg=%23fafafa&fg=%23222222&accent=%230a7cff")
            page.wait_for_selector("#empty", state="visible")
            assert page.get_attribute("html", "data-theme") == "light"
            body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            assert body_bg == "rgb(250, 250, 250)", body_bg
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#0a7cff"
            # live theme change through postMessage is ignored unless it comes from the embedding page
            page.evaluate("window.postMessage({type: 've-theme', theme: 'dark'}, '*')")
            page.wait_for_timeout(200)
            assert page.get_attribute("html", "data-theme") == "light"
            # drop a file onto the window: it is copied in and loaded
            page.evaluate("""async (url) => {
                const blob = await (await fetch(url)).blob()
                const dt = new DataTransfer()
                dt.items.add(new File([blob], 'dropped one.mp4', { type: 'video/mp4' }))
                window.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }))
                window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }))
            }""", "/api/media?t=%s&path=%s" % (srv.token, urllib.parse.quote(str(media["silent"]))))
            page.wait_for_selector("#video[data-src]", state="attached", timeout=90000)
            assert "dropped one.mp4" in page.inner_text("#file-chip")
            assert page.is_hidden("#empty")
            assert page.input_value("#in-outdir")                       # uploaded files default to the Videos folder
            assert not errors, errors
            browser.close()
    finally:
        srv.stop()
        for f in jobs_mod.UPLOAD_DIR.glob("dropped one*.mp4"):
            f.unlink()


def test_browser_tools_tab_lists_all_42_and_runs_one(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    try:
        with pw.sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:  # noqa: BLE001
                pytest.skip("no usable chromium: %s" % exc)
            page = browser.new_page(viewport={"width": 1500, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(srv.url(str(media["clip"])))
            page.wait_for_selector("#video[data-src]", state="attached", timeout=90000)
            page.click("#tabs button[data-tab=tools]")
            page.wait_for_selector(".tool-item")
            assert page.locator(".tool-item").count() == 42
            page.fill("#tool-search", "silence")
            assert 2 <= page.locator(".tool-item").count() < 42                 # search filters the list
            assert page.locator('.tool-item[data-tool="ve_detect_silence"]').count() == 1
            assert page.locator('.tool-item[data-tool="ve_remove_silence"]').count() == 1
            page.fill("#tool-search", "")
            page.click('.tool-item[data-tool="ve_trim"]')
            assert page.input_value("#tool-input").endswith("clip.mp4")          # current file is prefilled
            page.fill("#tool-fields .fld:has(label:text-is('duration')) input", "1")
            page.click("#tool-adv >> xpath=ancestor::details/summary")
            page.fill("#tool-adv .fld:has(label:text-is('output dir')) input", str(tmp_path / "from-ui"))
            page.click("#tool-run")
            page.wait_for_selector("#tool-result .ok", timeout=60000)
            assert len(list((tmp_path / "from-ui").glob("*.mp4"))) == 1
            assert not errors, errors
            browser.close()
    finally:
        srv.stop()
