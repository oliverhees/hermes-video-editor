"""Local HTTP server for the visual editor. Binds 127.0.0.1 only; every request needs a random token."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..core.ffmpeg import probe
from ..core.result import ToolError
from ..core.validate import get_num
from . import jobs as jobs_mod
from . import project as project_mod
from . import toolrun
from .security import MEDIA_EXTS, default_roots, inside, safe_dir, safe_media_file

WEB = Path(__file__).resolve().parent / "web"
STATIC = {"app.js": "text/javascript; charset=utf-8", "timeline.js": "text/javascript; charset=utf-8", "layers.js": "text/javascript; charset=utf-8", "overlays.js": "text/javascript; charset=utf-8", "help.js": "text/javascript; charset=utf-8",
          "app.css": "text/css; charset=utf-8"}
DOCS = Path(__file__).resolve().parents[1] / "docs"
HELP_DOCS = {"/help/en.md": DOCS / "en" / "GUIDE.md", "/help/de.md": DOCS / "de" / "GUIDE.md"}
MAX_BODY = 1 << 20
MIME_FIX = {".mkv": "video/x-matroska", ".mov": "video/quicktime", ".m4v": "video/mp4", ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4", ".flac": "audio/flac", ".opus": "audio/ogg", ".ts": "video/mp2t"}
HASH_RE = re.compile(r"^[0-9a-f]{16}$")
CACHE_FILES = {"thumbs.jpg": "image/jpeg", "proxy.mp4": "video/mp4", "proxy.webm": "video/webm"}


class EditorServer:
    def __init__(self, roots: Optional[List[str]] = None) -> None:
        self.roots: List[str] = list(roots or default_roots())
        self.roots.append(str(jobs_mod.UPLOAD_DIR))          # files dropped into the editor live here
        self.token = secrets.token_urlsafe(18)
        self.jobs = jobs_mod.JobRegistry()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, open_path: Optional[str] = None) -> str:
        from urllib.parse import quote
        base = "http://127.0.0.1:%d/?t=%s" % (self.port, self.token)
        return base + ("&open=" + quote(open_path, safe="")) if open_path else base

    def add_root(self, path: str) -> None:
        if not inside(path, self.roots):
            self.roots.append(path)

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


_lock = threading.Lock()
_instance: Optional[EditorServer] = None


def get_server() -> EditorServer:
    """Start the editor server once per process and reuse it."""
    global _instance
    with _lock:
        if _instance is None:
            _instance = EditorServer()
        return _instance


# --------------------------------------------------------------------------- API logic (pure-ish, testable)
def api_config(srv: EditorServer) -> Dict[str, Any]:
    from ..tools.export import EXPORT_PRESETS
    videos = Path.home() / "Videos"
    return {"home": str(Path.home()), "videos_dir": str(videos if videos.is_dir() else Path.home()), "roots": srv.roots, "presets": list(EXPORT_PRESETS),
            "reframes": list(jobs_mod.ASPECT_REFRAME), "speeds": list(jobs_mod.SPEEDS)}


def api_ls(srv: EditorServer, raw: Optional[str], kind: Optional[str] = None) -> Dict[str, Any]:
    exts = toolrun.KIND_EXTS.get(kind or "media", MEDIA_EXTS)
    folder = safe_dir(raw or str(Path.home()), srv.roots)
    dirs, files = [], []
    try:
        entries = sorted(os.scandir(str(folder)), key=lambda e: e.name.lower())
    except OSError as exc:
        raise ToolError("Cannot read folder: %s" % exc)
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                dirs.append({"name": e.name})
            elif ((e.name.endswith(".vproj.json") if kind == "project" else Path(e.name).suffix.lower() in exts)
                  and e.is_file()):
                files.append({"name": e.name, "size": e.stat().st_size})
        except OSError:
            continue
    parent = str(folder.parent) if inside(str(folder.parent), srv.roots) and folder.parent != folder else None
    return {"path": str(folder), "parent": parent, "dirs": dirs, "files": files}


def api_probe(srv: EditorServer, raw: Optional[str]) -> Dict[str, Any]:
    return probe(safe_media_file(raw, srv.roots))


def api_recent(srv: EditorServer) -> Dict[str, Any]:
    keep = [p for p in jobs_mod.recent_files() if inside(p, srv.roots)]
    return {"files": [{"path": p, "name": os.path.basename(p)} for p in keep]}


def api_upload_target(srv: EditorServer, name: str, length: int) -> Path:
    import shutil
    if length <= 0:
        raise ToolError("Empty upload.")
    target = jobs_mod.upload_target(name)
    free = shutil.disk_usage(str(target.parent)).free
    if length > free - (1 << 30):
        raise ToolError("Not enough free disk space for this file (%.1f GB needed)." % (length / 1e9),
                        hint="Use Open file... to pick the video from its folder instead (no copy needed).")
    return target


def api_prepare(srv: EditorServer, body: Dict[str, Any]) -> Dict[str, Any]:
    src = safe_media_file(body.get("path"), srv.roots)
    jobs_mod.remember(src)
    h264 = bool(body.get("h264", True))
    job = srv.jobs.start("prepare", lambda j: jobs_mod.prepare(j, src, h264))
    return {"job": job.id}


def api_silence(srv: EditorServer, body: Dict[str, Any]) -> Dict[str, Any]:
    from ..schemas import TOOLS
    src = safe_media_file(body.get("path"), srv.roots)
    handler = {t["name"]: t["handler"] for t in TOOLS}["lk_detect_silence"]
    res = json.loads(handler({"input": str(src), "noise_db": body.get("noise_db", -35),
                              "min_duration_s": body.get("min_silence_s", 0.5), "timeout_s": 600}))
    if not res.get("ok"):
        raise ToolError(res.get("error", "Silence detection failed"), res.get("hint"))
    return res["info"]


def api_project_save(srv: EditorServer, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "path": project_mod.save_project(body.get("path"), body.get("project"), srv.roots)}


def api_tool(srv: EditorServer, body: Dict[str, Any]) -> Dict[str, Any]:
    name = body.get("name")
    cfg = api_config(srv)
    args = toolrun.sanitize_args(str(name), body.get("args") or {}, srv.roots, cfg["videos_dir"], str(jobs_mod.UPLOAD_DIR))

    def work(job: jobs_mod.Job) -> None:
        job.step = str(name)
        job.result = toolrun.run_tool(str(name), args)

    return {"job": srv.jobs.start("tool", work).id}


def api_export(srv: EditorServer, body: Dict[str, Any]) -> Dict[str, Any]:
    if body.get("clips") is not None:                       # timeline export
        body = dict(body, clips_info=project_mod.sanitize_clips(body["clips"], srv.roots), cuts=[],
                    canvas=project_mod.sanitize_canvas(body.get("canvas")), bg=project_mod.sanitize_bg(body.get("bg")),
                    texts=project_mod.sanitize_texts(body.get("texts")), audios_info=project_mod.sanitize_audios(body.get("audios"), srv.roots),
                    overlays_info=project_mod.sanitize_overlays(body.get("overlays"), srv.roots))
        src = Path(body["clips_info"][0]["path"])
        default_dir = Path(api_config(srv)["videos_dir"]) if inside(str(src), [str(jobs_mod.UPLOAD_DIR)]) else src.parent
    else:
        src = safe_media_file(body.get("path"), srv.roots)
        default_dir = src.parent
    jobs_mod.validate_export(body)
    out_dir = safe_dir(body["output_dir"], srv.roots, create=True) if body.get("output_dir") else default_dir
    job = srv.jobs.start("export", lambda j: jobs_mod.run_export(j, src, body, out_dir))
    return {"job": job.id}


# --------------------------------------------------------------------------- HTTP plumbing
def parse_range(header: Optional[str], size: int) -> Optional[Tuple[int, int]]:
    """'bytes=a-b' -> (start, end) inclusive, or None for no/invalid range. Raises ValueError if unsatisfiable."""
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    a, _, b = spec.partition("-")
    try:
        if a == "":
            length = int(b)
            start, end = max(0, size - length), size - 1
        else:
            start = int(a)
            end = int(b) if b else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start > end or start >= size:
        raise ValueError("unsatisfiable")
    return start, end


def make_handler(srv: EditorServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VideoEditor/0.1"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # silence request logging
            pass

        # -- helpers
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors()
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: Any, status: int = 200) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _error(self, status: int, message: str, hint: str = "") -> None:
            self._json({"ok": False, "error": message, "hint": hint}, status)

        def _authorized(self, query: Dict[str, List[str]], path: str = "") -> bool:
            host = (self.headers.get("Host") or "").lower()
            if host not in ("127.0.0.1:%d" % srv.port, "localhost:%d" % srv.port):
                return False                      # DNS-rebinding guard
            if path.startswith("/static/"):       # app.js / app.css only: public code, no user data
                return True
            token = (query.get("t") or [""])[0]
            return secrets.compare_digest(token, srv.token)

        def _serve_file(self, path: Path, ctype: Optional[str] = None) -> None:
            size = path.stat().st_size
            ctype = ctype or MIME_FIX.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            try:
                rng = parse_range(self.headers.get("Range"), size)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self._cors()
                self.end_headers()
                return
            start, end = rng if rng else (0, size - 1)
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if rng:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            try:
                with open(str(path), "rb") as fh:
                    fh.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(262144, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # -- routing
        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            self._route("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._route("POST")

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if not self._authorized(query, url.path):
                self._error(403, "Forbidden", "Open the editor from the link the plugin gives you (it contains a one-time token).")
                return
            route = url.path
            try:
                if method == "GET":
                    self._get(route, query)
                elif route == "/api/upload":
                    self._upload(query)
                else:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > MAX_BODY:
                        self._error(413, "Request too large")
                        return
                    raw = self.rfile.read(length) if length else b"{}"
                    try:
                        body = json.loads(raw.decode("utf-8") or "{}")
                    except ValueError:
                        self._error(400, "Invalid JSON")
                        return
                    if not isinstance(body, dict):
                        self._error(400, "JSON object expected")
                        return
                    self._post(route, body)
            except ToolError as exc:
                self._error(400, exc.message, exc.hint or "")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:  # noqa: BLE001
                self._error(500, "%s: %s" % (type(exc).__name__, exc))

        def _upload(self, q: Dict[str, List[str]]) -> None:
            """Stream a dropped file to disk (browsers do not expose real paths for dropped files)."""
            length = int(self.headers.get("Content-Length") or 0)
            target = api_upload_target(srv, (q.get("name") or [""])[0], length)
            tmp = target.with_name(target.name + ".part")
            left = length
            try:
                with open(str(tmp), "wb") as fh:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        fh.write(chunk)
                        left -= len(chunk)
                if left:
                    raise ToolError("Upload was interrupted.")
                os.replace(str(tmp), str(target))
            finally:
                if tmp.exists():
                    tmp.unlink()
            self._json({"ok": True, "path": str(target)})

        def _get(self, route: str, q: Dict[str, List[str]]) -> None:
            first = lambda k: (q.get(k) or [None])[0]  # noqa: E731
            if route == "/":
                self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8",
                           {"Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self'; "
                                                       "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'"})
            elif route.startswith("/static/") and route[8:] in STATIC:
                self._send(200, (WEB / route[8:]).read_bytes(), STATIC[route[8:]])
            elif route in HELP_DOCS:                                  # the user guide, one markdown file per language
                self._send(200, HELP_DOCS[route].read_bytes(), "text/markdown; charset=utf-8")
            elif route == "/api/config":
                self._json(api_config(srv))
            elif route == "/api/ls":
                self._json(api_ls(srv, first("path"), first("kind")))
            elif route == "/api/tools":
                self._json({"tools": toolrun.tool_catalog(), "groups": [t for _, t in toolrun.GROUPS]})
            elif route == "/api/probe":
                self._json(api_probe(srv, first("path")))
            elif route == "/api/project/load":
                self._json(project_mod.load_project(first("path"), srv.roots))
            elif route == "/api/recent":
                self._json(api_recent(srv))
            elif route == "/api/media":
                self._serve_file(safe_media_file(first("path"), srv.roots))
            elif route == "/api/cache":
                cid, name = first("id") or "", first("name") or ""
                if not HASH_RE.match(cid) or name not in CACHE_FILES:
                    raise ToolError("Unknown cache file.")
                p = jobs_mod.CACHE_ROOT / cid / name
                if not p.is_file():
                    self._error(404, "Not ready yet")
                    return
                self._serve_file(p, CACHE_FILES[name])
            elif route == "/api/waveform":
                cid = first("id") or ""
                p = jobs_mod.CACHE_ROOT / cid / "waveform.json"
                if not HASH_RE.match(cid) or not p.is_file():
                    self._error(404, "Not ready yet")
                    return
                self._serve_file(p, "application/json")
            elif route == "/api/job":
                job = srv.jobs.get(first("id") or "")
                if not job:
                    self._error(404, "Unknown job")
                    return
                d = job.to_dict()
                d["result"] = {k: v for k, v in d["result"].items() if k != "waveform"}   # waveform has its own route
                d["result"]["has_waveform"] = bool(job.result.get("waveform"))
                self._json(d)
            else:
                self._error(404, "Not found")

        def _post(self, route: str, body: Dict[str, Any]) -> None:
            if route == "/api/prepare":
                self._json(api_prepare(srv, body))
            elif route == "/api/silence":
                get_num(body, "noise_db", -35, lo=-90, hi=0)
                get_num(body, "min_silence_s", 0.5, lo=0.05, hi=3600)
                self._json(api_silence(srv, body))
            elif route == "/api/export":
                self._json(api_export(srv, body))
            elif route == "/api/tool":
                self._json(api_tool(srv, body))
            elif route == "/api/project/save":
                self._json(api_project_save(srv, body))
            else:
                self._error(404, "Not found")

    return Handler
