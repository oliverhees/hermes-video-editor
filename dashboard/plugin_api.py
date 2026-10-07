"""Backend route for the Desktop page: starts the local editor server and returns its URL.

Mounted by Hermes at /api/plugins/hermes-video-editor/ (see desktop/plugin.js, which calls ctx.rest('/start')).
"""
import importlib.util
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter()
_PKG = "hermes_video_editor_ui"


def _server():
    """Load this plugin folder as a package (it has a hyphen in its name) and return the editor server."""
    if _PKG not in sys.modules:
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(_PKG, root / "__init__.py", submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PKG] = module
        spec.loader.exec_module(module)
    from importlib import import_module
    return import_module(_PKG + ".editor.server").get_server()


@router.get("/start")
def start(open: Optional[str] = None):  # noqa: A002 - query parameter name used by the UI
    try:
        srv = _server()
        if open:
            srv.add_root(str(Path(open).expanduser().resolve().parent))
        return {"url": srv.url(open), "port": srv.port}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="%s: %s" % (type(exc).__name__, exc))


@router.get("/status")
def status():
    return {"loaded": _PKG in sys.modules}
