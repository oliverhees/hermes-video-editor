"""Hermes-facing pieces: dashboard API route, Desktop plugin.js (with a stubbed SDK), and a real-browser run."""
import json
import subprocess
import shutil
import urllib.parse
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import ROOT, ffprobe, needs_ffmpeg
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
    assert "querySelector" not in src and "styleSheets" not in src and "cssRules" not in src, "no lookups in the app's own UI or style sheets"


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
    assert '<a id="powered" href="https://lokyy.de" target="_blank" rel="noopener noreferrer">Powered by Lokyy.de</a><span class="tag">German Hermes Engineering</span>' in html
    js = (ROOT / "editor" / "web" / "app.js").read_text()
    assert 'type: "ve-open-link"' in js
    assert "Powered by [Lokyy.de](https://lokyy.de) - German Hermes Engineering" in (ROOT / "README.md").read_text()


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
    link = '<a id="powered" href="https://lokyy.de" target="_blank" rel="noopener noreferrer">Powered by Lokyy.de</a><span class="tag">German Hermes Engineering</span>'
    assert link in html
    rest = html.replace(link, "")                                   # the only external address is the credit link
    assert "<script>" not in rest and "http://" not in rest and "https://" not in rest


# ---------------------------------------------------------------- real browser (optional)
def browser(pw_mod, viewport=(1500, 900)):
    p = pw_mod.sync_playwright().start()
    try:
        b = p.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        p.stop()
        pytest.skip("no usable chromium: %s" % exc)
    page = b.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return p, b, page, errors


def state(page, expr):
    return page.evaluate("(() => { const s = window.__ve.state; const TL = window.__ve.TL; return %s })()" % expr)


def wait_ready(page, n_clips=1):
    page.wait_for_selector("#video[data-src]", state="attached", timeout=90000)
    for _ in range(100):
        if state(page, "s.clips.length") >= n_clips:
            return
        page.wait_for_timeout(100)
    raise AssertionError("clips were not added")


def bbox(page, selector):
    """Bounding box of an element that may be re-rendered at any moment: retry a few times."""
    for _ in range(30):
        try:
            box = page.locator(selector).bounding_box(timeout=1000)
        except Exception:  # noqa: BLE001 - detached while measuring
            box = None
        if box:
            return box
        page.wait_for_timeout(100)
    raise AssertionError("no element for " + selector)


def add_clip_via_dialog(page, path):
    page.click("#btn-open")
    page.fill("#dlg-path", str(path))
    page.press("#dlg-path", "Enter")


def test_browser_timeline_edit_reorder_trim_undo_and_export(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["gap"])))                         # 4 s, silence from 1.0 to 2.5 s
        wait_ready(page)
        assert state(page, "s.clips.length") == 1 and abs(state(page, "TL.total(s.clips)") - 4) < 0.3
        # split at 2 s with the keyboard, then delete the second half
        page.evaluate("window.__ve.seek(2)")
        page.keyboard.press("s")
        assert state(page, "s.clips.length") == 2 and state(page, "s.sel") == 1
        page.keyboard.press("Delete")
        assert state(page, "s.clips.length") == 1 and abs(state(page, "TL.total(s.clips)") - 2) < 0.05
        page.keyboard.press("Control+z")                              # undo the delete
        assert state(page, "s.clips.length") == 2 and abs(state(page, "TL.total(s.clips)") - 4) < 0.05
        page.keyboard.press("Control+Shift+z")                        # redo it
        assert state(page, "s.clips.length") == 1
        page.keyboard.press("Control+z")
        # add a second file: it is inserted after the selected clip (the undo restored the selection on the 2nd half)
        add_clip_via_dialog(page, media["other"])                     # 2 s, different size/fps/sample rate
        for _ in range(100):
            if state(page, "s.clips.length") == 3:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.clips.length") == 3
        assert [state(page, "s.assets[s.clips[%d].asset].name" % i) for i in range(3)] == ["gap.mp4", "gap.mp4", "other.mp4"]
        total_before = state(page, "TL.total(s.clips)")
        assert total_before == pytest.approx(6, abs=0.35)
        # reorder by dragging the 'other' clip (now the last one) to the very start
        box = bbox(page, ".clip >> nth=2")
        first = bbox(page, ".clip >> nth=0")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 30)
        page.mouse.down()
        page.mouse.move(first["x"] + 6, box["y"] + 30, steps=8)
        page.mouse.up()
        assert [state(page, "s.assets[s.clips[%d].asset].name" % i) for i in range(3)] == ["other.mp4", "gap.mp4", "gap.mp4"]
        # trim the right edge of the first clip by dragging its handle to the left
        c0 = bbox(page, ".clip >> nth=0")
        page.mouse.move(c0["x"] + c0["width"] - 3, c0["y"] + 30)
        page.mouse.down()
        page.mouse.move(c0["x"] + c0["width"] - 3 - 110, c0["y"] + 30, steps=6)
        page.mouse.up()
        after_trim = state(page, "TL.total(s.clips)")
        assert after_trim < total_before - 0.2                        # ripple: the timeline got shorter
        page.keyboard.press("Control+z")
        assert state(page, "TL.total(s.clips)") == pytest.approx(total_before, abs=0.01)
        # remove silences: the gap clips lose their silent middle
        page.click("#tabs button[data-tab=cuts]")
        page.click("#ruler", position={"x": 10, "y": 10})                # clicking the ruler deselects: silence removal then covers every clip
        assert state(page, "s.sel") == -1
        page.click("#btn-silence")
        for _ in range(100):
            if state(page, "s.clips.length") > 3:
                break
            page.wait_for_timeout(100)
        assert state(page, "TL.total(s.clips)") < total_before - 1.0
        # save the project, reload it from the file
        page.click("#btn-saveas")
        page.fill("#dlg-name", "demo timeline")
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        for _ in range(50):                                            # the folder listing is loaded asynchronously
            if state(page, "s.dlgProjectPath") == str(tmp_path):
                break
            page.wait_for_timeout(100)
        page.click("#dlg-usefolder")
        saved = tmp_path / "demo timeline.vproj.json"
        for _ in range(50):
            if saved.exists():
                break
            page.wait_for_timeout(100)
        assert saved.exists()
        clips_now = state(page, "s.clips.length")
        total_now = state(page, "TL.total(s.clips)")
        # export what is on the timeline
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "timeline-export"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=120000)
        out = list((tmp_path / "timeline-export").glob("*.mp4"))
        assert len(out) == 1 and ffprobe(out[0])["duration"] == pytest.approx(total_now, abs=0.5)
        page2 = b.new_page(viewport={"width": 1500, "height": 900})
        page2.on("pageerror", lambda e: errors.append(str(e)))
        page2.goto(srv.url() + "&project=" + urllib.parse.quote(str(saved)))
        for _ in range(100):
            if state(page2, "s.clips.length") == clips_now:
                break
            page2.wait_for_timeout(100)
        assert state(page2, "s.clips.length") == clips_now
        assert state(page2, "TL.total(s.clips)") == pytest.approx(total_now, abs=0.01)
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_browser_playback_crosses_clip_boundaries(media):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"])])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["clip"])))
        wait_ready(page)
        add_clip_via_dialog(page, media["other"])
        for _ in range(100):
            if state(page, "s.clips.length") == 2:
                break
            page.wait_for_timeout(100)
        # wait until both previews are ready, then play across the boundary at 4 s
        for _ in range(300):
            if state(page, "Object.values(s.assets).every(a => a.src)"):
                break
            page.wait_for_timeout(100)
        page.evaluate("window.__ve.seek(3.2)")
        page.click("#btn-play")
        for _ in range(150):
            if state(page, "s.t") > 4.6:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.t") > 4.6, "playback did not continue into the second clip"
        page.click("#btn-play")                                       # pause
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_browser_theme_empty_state_and_drop(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"])])
    p, b, page, errors = browser(pw, (1400, 800))
    try:
        page.goto(srv.url() + "&theme=light&bg=%23fafafa&fg=%23222222&accent=%230a7cff")   # light theme + app colours arrive through the URL
        page.wait_for_selector("#empty", state="visible")
        assert page.get_attribute("html", "data-theme") == "light"
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(250, 250, 250)"
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()") == "#0a7cff"
        page.evaluate("window.postMessage({type: 've-theme', theme: 'dark'}, '*')")             # ignored unless it comes from an embedding page
        page.wait_for_timeout(200)
        assert page.get_attribute("html", "data-theme") == "light"
        # drop two files at once: both are copied in and appended to the timeline
        page.evaluate("""async ([u1, u2]) => {
            const dt = new DataTransfer()
            for (const [u, n] of [[u1, 'dropped one.mp4'], [u2, 'dropped two.mp4']]) {
                const blob = await (await fetch(u)).blob(); dt.items.add(new File([blob], n, { type: 'video/mp4' }))
            }
            window.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }))
            window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }))
        }""", ["/api/media?t=%s&path=%s" % (srv.token, urllib.parse.quote(str(media[k]))) for k in ("silent", "clip")])
        for _ in range(300):
            if state(page, "s.clips.length") == 2:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.clips.length") == 2
        assert [state(page, "s.assets[s.clips[%d].asset].name" % i) for i in range(2)] == ["dropped one.mp4", "dropped two.mp4"]
        assert page.is_hidden("#empty")
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()
        for f in jobs_mod.UPLOAD_DIR.glob("dropped *.mp4"):
            f.unlink()


def test_browser_tools_tab_lists_all_42_and_runs_one(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw, (1500, 900))
    try:
        page.goto(srv.url(str(media["clip"])))
        wait_ready(page)
        page.click("#tabs button[data-tab=tools]")
        page.wait_for_selector(".tool-item")
        assert page.locator(".tool-item").count() == 42
        page.fill("#tool-search", "silence")
        assert 2 <= page.locator(".tool-item").count() < 42
        assert page.locator('.tool-item[data-tool="lk_detect_silence"]').count() == 1
        assert page.locator('.tool-item[data-tool="lk_remove_silence"]').count() == 1
        page.fill("#tool-search", "")
        page.click('.tool-item[data-tool="lk_trim"]')
        assert page.input_value("#tool-input").endswith("clip.mp4")          # the clip under the playhead is prefilled
        page.fill("#tool-fields .fld:has(label:text-is('duration')) input", "1")
        page.click("#tool-adv >> xpath=ancestor::details/summary")
        page.fill("#tool-adv .fld:has(label:text-is('output dir')) input", str(tmp_path / "from-ui"))
        page.click("#tool-run")
        page.wait_for_selector("#tool-result .ok", timeout=60000)
        assert len(list((tmp_path / "from-ui").glob("*.mp4"))) == 1
        page.click("#tool-result button:has-text('Add result to timeline')")
        for _ in range(100):
            if state(page, "s.clips.length") == 2:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.clips.length") == 2
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


@pytest.mark.skipif(not NODE, reason="node is not installed")
def test_desktop_page_finds_the_apps_own_accent_colour(tmp_path):
    """The editor must use Hermes' accent, not a built-in colour. Fake DOM: only a vivid variable counts."""
    src = (ROOT / "desktop" / "plugin.js").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.startswith("import ")).replace("export default", "const plugin_default =")
    script = textwrap.dedent("""
        const sdk = {}, jsxRuntime = {}, React = {}
        // fake browser: custom properties resolve through VARS; the canvas returns the rgb() it was given
        const VARS = { '--background': 'rgb(250, 250, 250)', '--primary-foreground': 'rgb(255, 255, 255)', '--ring': 'rgb(120, 120, 120)',
                       '--accent': 'rgb(240, 240, 245)', '--primary': 'rgb(109, 63, 210)', '--link': 'rgb(0, 0, 255)' }
        const spans = []
        const document = {
          body: { appendChild(n) {}, removeChild(n) {} },
          createElement(tag) {
            if (tag === 'canvas') { let last = ''; return { width: 0, height: 0, getContext: () => ({ clearRect() {}, set fillStyle(v) { last = v }, fillRect() {},
              getImageData: () => { const m = /rgb\\((\\d+), (\\d+), (\\d+)\\)/.exec(last); return { data: m ? [+m[1], +m[2], +m[3], 255] : [0, 0, 0, 0] } } }) } }
            const span = { style: { color: '' } }; spans.push(span); return span
          },
        }
        const getComputedStyle = n => ({ color: (/var\\((--[\\w-]+)\\)/.exec(n.style && n.style.color) || [])[1] ? (VARS[/var\\((--[\\w-]+)\\)/.exec(n.style.color)[1]] || 'rgb(29, 35, 48)') : 'rgb(29, 35, 48)',
                                         backgroundColor: 'rgb(250, 250, 250)' })
        %s
        const hex = findAccent()
        if (hex !== '#6d3fd2') throw new Error('wrong accent: ' + hex)       // --accent is a pale grey (not vivid), --primary is the violet one
        if (!isVivid('#6d3fd2') || isVivid('#f0f0f5') || isVivid('#777777') || isVivid('#ffffff') || isVivid('#000000')) throw new Error('isVivid wrong')
        VARS['--primary'] = 'rgb(240, 240, 240)'
        VARS['--link'] = 'rgb(0, 0, 255)'
        if (findAccent() !== '#0000ff') throw new Error('fallback to the next vivid variable failed')
        VARS['--link'] = 'rgb(10, 10, 10)'
        if (findAccent() !== null) throw new Error('should find nothing')
        const theme = readTheme(null)
        if (theme.theme !== 'light' || theme.bg !== '#fafafa' || 'accent' in theme) throw new Error('readTheme: ' + JSON.stringify(theme))
        console.log('OK')
        """) % body
    r = run_node(script, tmp_path)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


def test_browser_canvas_transform_background_and_export(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["clip"])))                        # 640x360, 4 s
        wait_ready(page)
        page.click("#tabs button[data-tab=picture]")
        page.select_option("#in-aspect", "9:16")
        page.select_option("#in-short", "360")
        assert state(page, "s.canvas.aspect") == "9:16" and "360 × 640" in page.inner_text("#canvas-size")
        # background colour shows in the preview next to the (fitted) picture
        page.select_option("#in-bg", "color")
        page.evaluate("document.getElementById('in-bgcolor').value = '#ff0000'; document.getElementById('in-bgcolor').dispatchEvent(new Event('change'))")
        page.evaluate("window.__ve.seek(1)")
        page.wait_for_timeout(800)
        px = page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(3, 3, 1, 1).data; return [d[0], d[1], d[2]] })()")
        assert px[0] > 200 and px[1] < 40 and px[2] < 40, px
        # drag the picture with the mouse: position changes and can be undone
        gz = bbox(page, "#gizmo")
        page.mouse.move(gz["x"] + gz["width"] / 2, gz["y"] + gz["height"] / 2)
        page.mouse.down()
        page.mouse.move(gz["x"] + gz["width"] / 2 + 40, gz["y"] + gz["height"] / 2 - 90, steps=6)
        page.mouse.up()
        tf = state(page, "s.clips[0].tf")
        assert tf["x"] > 0.05 and tf["y"] < -0.1 and tf["s"] == 1
        page.keyboard.press("Control+z")
        assert state(page, "!s.clips[0].tf || s.clips[0].tf.x === 0")
        # zoom with the mouse wheel, then with the Fill button
        page.mouse.move(gz["x"] + gz["width"] / 2, gz["y"] + gz["height"] / 2)
        page.mouse.wheel(0, -300)
        assert state(page, "s.clips[0].tf.s") > 1.3
        page.click("#btn-tf-fill")
        assert state(page, "s.clips[0].tf.s") == pytest.approx(state(page, "TL.fillScale(640, 360, 360, 640)"), abs=0.01)
        page.click("#btn-tf-reset")
        # split: each piece gets its own position
        page.evaluate("window.__ve.seek(2)")
        page.keyboard.press("s")
        assert state(page, "s.clips.length") == 2 and state(page, "s.sel") == 1
        page.click("#btn-tf-fill")
        assert state(page, "s.clips[1].tf.s") > 3
        assert state(page, "!s.clips[0].tf || s.clips[0].tf.s === 1")
        # export with the chosen canvas, background and the different positions
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "vertical"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=120000)
        out = list((tmp_path / "vertical").glob("*.mp4"))
        assert len(out) == 1
        v = ffprobe(out[0])
        assert (v["video"]["width"], v["video"]["height"]) == (360, 640)
        top = subprocess.run(["ffmpeg", "-v", "error", "-ss", "0.5", "-i", str(out[0]), "-frames:v", "1", "-vf", "crop=iw:ih*0.1:0:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        n = len(top) // 3
        assert sum(top[0::3]) / n > 200 and sum(top[1::3]) / n < 40            # red bars above the fitted first clip
        later = subprocess.run(["ffmpeg", "-v", "error", "-ss", "3.0", "-i", str(out[0]), "-frames:v", "1", "-vf", "crop=iw:ih*0.1:0:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               capture_output=True, check=True).stdout
        assert sum(later[1::3]) / (len(later) // 3) > 30                         # second clip is zoomed to fill: no red bars
        # project file keeps canvas, background and the transforms
        page.click("#btn-saveas")
        page.fill("#dlg-name", "vertical")
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        for _ in range(50):
            if state(page, "s.dlgProjectPath") == str(tmp_path):
                break
            page.wait_for_timeout(100)
        page.click("#dlg-usefolder")
        saved = tmp_path / "vertical.vproj.json"
        for _ in range(50):
            if saved.exists():
                break
            page.wait_for_timeout(100)
        data = json.loads(saved.read_text())
        assert data["canvas"] == {"aspect": "9:16", "short": 360} and data["bg"] == {"mode": "color", "color": "#ff0000"}
        assert data["clips"][1]["tf"]["s"] > 3
        page2 = b.new_page(viewport={"width": 1500, "height": 900})
        page2.on("pageerror", lambda e: errors.append(str(e)))
        page2.goto(srv.url() + "&project=" + urllib.parse.quote(str(saved)))
        for _ in range(100):
            if state(page2, "s.clips.length") == 2:
                break
            page2.wait_for_timeout(100)
        assert state(page2, "s.canvas.aspect") == "9:16" and state(page2, "s.bg.color") == "#ff0000" and state(page2, "s.clips[1].tf.s") > 3
        assert page2.input_value("#in-aspect") == "9:16"
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_browser_text_and_audio_layers(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    music = tmp_path / "music.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=3", str(music)], check=True)
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["clip"])))
        wait_ready(page)
        # text: add, edit, move on the lane, undo
        page.evaluate("window.__ve.seek(1)")
        page.click("#tabs button[data-tab=text]")
        page.click("#btn-text-add")
        page.fill("#tx-text", "Hello Lokyy")
        assert state(page, "s.texts.length") == 1 and state(page, "s.texts[0].text") == "Hello Lokyy"
        assert state(page, "s.texts[0].start") == pytest.approx(1, abs=0.05)
        page.click("#tx-p-lower")
        assert state(page, "s.texts[0].box") is True
        page.keyboard.press("Escape")
        page.click("#btn-text-dup")
        assert state(page, "s.texts.length") == 2
        page.click("#btn-text-del")
        assert state(page, "s.texts.length") == 1
        page.keyboard.press("Control+z")
        assert state(page, "s.texts.length") == 2
        page.keyboard.press("Control+z")
        assert state(page, "s.texts.length") == 1
        # audio: add through the dialog, set level, lane item exists
        page.click("#tabs button[data-tab=sound]")
        page.click("#btn-audio-add")
        page.fill("#dlg-path", str(music))
        page.press("#dlg-path", "Enter")
        for _ in range(100):
            if state(page, "s.audios.length") == 1:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.audios.length") == 1
        page.wait_for_selector("#audios .aitem", timeout=5000)
        page.fill("#au-vol", "-6")
        page.dispatch_event("#au-vol", "input")
        assert state(page, "s.audios[0].vol") == -6
        # export: text window drawn, music mixed in
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "layered"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=120000)
        out = list((tmp_path / "layered").glob("*.mp4"))
        assert len(out) == 1
        assert ffprobe(out[0])["audio"] is not None
        # project keeps both layers
        page.click("#btn-saveas")
        page.fill("#dlg-name", "layers")
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        for _ in range(50):
            if state(page, "s.dlgProjectPath") == str(tmp_path):
                break
            page.wait_for_timeout(100)
        page.click("#dlg-usefolder")
        saved = tmp_path / "layers.vproj.json"
        for _ in range(50):
            if saved.exists():
                break
            page.wait_for_timeout(100)
        data = json.loads(saved.read_text())
        assert data["texts"][0]["text"] == "Hello Lokyy" and data["audios"][0]["vol"] == -6
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_browser_overlay_track(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    red = tmp_path / "red.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:r=25:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(red)], check=True)
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["clip"])))
        wait_ready(page)
        page.evaluate("window.__ve.seek(1)")
        page.click("#tabs button[data-tab=overlay]")
        page.click("#btn-ov-add")
        page.fill("#dlg-path", str(red))
        page.press("#dlg-path", "Enter")
        for _ in range(100):
            if state(page, "s.overlays.length") == 1:
                break
            page.wait_for_timeout(100)
        assert state(page, "s.overlays.length") == 1 and state(page, "s.overlays[0].start") == pytest.approx(1, abs=0.05)
        page.wait_for_selector("#ovs .oitem", timeout=5000)

        def stage_px(fx, fy):
            return page.evaluate("(() => { const c = document.getElementById('stage-canvas'); const d = c.getContext('2d').getImageData(Math.round(c.width*%s), Math.round(c.height*%s), 1, 1).data; return [d[0], d[1], d[2]] })()" % (fx, fy))
        red_seen = False
        for _ in range(40):                                   # the overlay video needs a moment to load its frame
            page.evaluate("window.__ve.seek(1.5)")
            page.wait_for_timeout(250)
            px = stage_px(0.77, 0.23)
            if px[0] > 200 and px[1] < 60:
                red_seen = True
                break
        assert red_seen, px
        # drag it on the preview, undo, resize by slider, opacity
        gz = bbox(page, "#ogizmo")
        page.mouse.move(gz["x"] + gz["width"] / 2, gz["y"] + gz["height"] / 2)
        page.mouse.down()
        page.mouse.move(gz["x"] + gz["width"] / 2 - 150, gz["y"] + gz["height"] / 2 + 60, steps=6)
        page.mouse.up()
        tf = state(page, "s.overlays[0].tf")
        assert tf["x"] < 0.2 and tf["y"] > -0.2
        page.keyboard.press("Control+z")
        assert state(page, "s.overlays[0].tf.x") == pytest.approx(0.27, abs=0.001)
        page.click("#ov-c-bl")
        assert state(page, "s.overlays[0].tf.x") == -0.27 and state(page, "s.overlays[0].tf.y") == 0.27
        page.fill("#ov-s", "50")
        page.dispatch_event("#ov-s", "input")
        assert state(page, "s.overlays[0].tf.s") == 0.5
        # lane: move with the mouse
        it = bbox(page, "#ovs .oitem")
        page.mouse.move(it["x"] + it["width"] / 2, it["y"] + it["height"] / 2)
        page.mouse.down()
        page.mouse.move(it["x"] + it["width"] / 2 + 40, it["y"] + it["height"] / 2, steps=4)
        page.mouse.up()
        assert state(page, "s.overlays[0].start") > 1.05
        # export + project
        page.click("#tabs button[data-tab=export]")
        page.fill("#in-outdir", str(tmp_path / "pip"))
        page.click("#btn-export")
        page.wait_for_selector("#result .ok", timeout=120000)
        assert len(list((tmp_path / "pip").glob("*.mp4"))) == 1
        page.click("#btn-saveas")
        page.fill("#dlg-name", "pip")
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        for _ in range(50):
            if state(page, "s.dlgProjectPath") == str(tmp_path):
                break
            page.wait_for_timeout(100)
        page.click("#dlg-usefolder")
        saved = tmp_path / "pip.vproj.json"
        for _ in range(50):
            if saved.exists():
                break
            page.wait_for_timeout(100)
        data = json.loads(saved.read_text())
        assert data["overlays"][0]["tf"]["s"] == 0.5 and data["overlays"][0]["tf"]["x"] == -0.27
        # delete with the keyboard
        page.click("#ovs .oitem")
        page.keyboard.press("Delete")
        assert state(page, "s.overlays.length") == 0
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_docs_are_bilingual_and_consistent():
    import re
    for lang in ("en", "de"):
        for name in ("GUIDE.md", "TOOLS.md"):
            assert (ROOT / "docs" / lang / name).is_file(), (lang, name)
    en, de = [(ROOT / "docs" / l / "GUIDE.md").read_text(encoding="utf-8") for l in ("en", "de")]
    heads = lambda t: [h for h in re.findall(r"^## (\d+)\.", t, re.M)]
    assert heads(en) == heads(de) and len(heads(en)) >= 12            # same chapters in both languages
    for text in (en, de):
        assert "PolyForm" in text and "https://lokyy.de" in text and "lk_" in text and not re.search(r"\bve_", text)
    readme_en, readme_de = [(ROOT / n).read_text(encoding="utf-8") for n in ("README.md", "README.de.md")]
    for t in (readme_en, readme_de):
        for link in ("docs/en/GUIDE.md", "docs/de/GUIDE.md", "docs/en/TOOLS.md", "docs/de/TOOLS.md", "LICENSE"):
            assert "(%s)" % link in t, link
        assert "(README.de.md)" in readme_en and "(README.md)" in readme_de
        assert "PolyForm" in t
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert lic.startswith("# PolyForm Noncommercial License 1.0.0") and "Required Notice" in lic and "MIT" not in lic
    assert "PolyForm-Noncommercial-1.0.0" in (ROOT / "plugin.yaml").read_text(encoding="utf-8")


def test_catalog_entry_links_the_docs(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "make_catalog_entry.py")], capture_output=True, text=True, check=True).stdout
    assert "docs_url: https://github.com/oliverhees/hermes-video-editor/blob/" in out and "PolyForm" in out and "\n    - ve_" not in out and "lk_trim" in out


def test_browser_help_in_english_and_german(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url())
        page.wait_for_selector("#btn-help")
        page.click("#btn-help")
        page.wait_for_selector("#help-body h1", timeout=10000)
        assert "user guide" in page.inner_text("#help-body h1").lower() and page.locator("#help-body table").count() >= 4
        page.click("#help-de")
        for _ in range(100):
            if "Anleitung" in page.inner_text("#help-body"):
                break
            page.wait_for_timeout(100)
        assert "Leinwand" in page.inner_text("#help-body")
        assert page.locator("#help-body script").count() == 0 and "<" not in page.inner_text("#help-body h1")
        page.keyboard.press("Escape")
        assert page.is_hidden("#help")
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()


def test_browser_open_project_differs_from_add_clip(media, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from hermes_video_editor.editor.server import EditorServer
    (tmp_path / "old.vproj.json").write_text(json.dumps({"version": 1, "assets": {"a": {"path": str(media["clip"])}}, "clips": [{"id": "c", "asset": "a", "in": 0, "out": 2}]}))
    srv = EditorServer(roots=[str(media["dir"]), str(tmp_path)])
    p, b, page, errors = browser(pw)
    try:
        page.goto(srv.url(str(media["clip"])))
        wait_ready(page)
        page.click("#btn-open")                                   # add clip: videos of the media folder, hint says so
        assert "video or audio file" in page.inner_text("#dlg-hint")
        page.fill("#dlg-path", str(media["dir"]))
        page.press("#dlg-path", "Enter")
        page.wait_for_selector("#dlg-list .item:has-text('clip.mp4')")
        page.click("#dlg-close")
        page.click("#btn-openproj")                               # open project: only project files, own folder, own hint
        assert "project" in page.inner_text("#dlg-hint").lower() and "replaces" in page.inner_text("#dlg-hint")
        assert page.inner_text("#dlg-title") == "Open a project"
        page.fill("#dlg-path", str(tmp_path))
        page.press("#dlg-path", "Enter")
        page.wait_for_selector("#dlg-list .item:has-text('old.vproj.json')")
        assert page.locator("#dlg-list .item:has-text('.mp4')").count() == 0
        page.click("#dlg-close")
        page.click("#btn-open")                                   # the media dialog did not follow the project folder
        page.wait_for_selector("#dlg-list .item:has-text('clip.mp4')")
        assert not errors, errors
    finally:
        b.close()
        p.stop()
        srv.stop()
