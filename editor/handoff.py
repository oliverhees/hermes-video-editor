"""Hand-over from the agent to the editor: the tool lk_open_in_editor puts a request in a small file queue, the editor (or the
Hermes Desktop page, which may live in another process) picks it up. Nothing here starts a window by itself."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

def queue_file() -> Path:
    """Same place for every process (agent, dashboard, standalone editor); VE_QUEUE_DIR overrides it for tests."""
    base = os.environ.get("VE_QUEUE_DIR") or str(Path(tempfile.gettempdir()) / "hermes-video-editor-cache")
    return Path(base) / "open_requests.json"


MAX_ENTRIES, MAX_AGE_S = 20, 24 * 3600
SETTINGS = {"focus_editor": True}              # filled from the plugin settings by register()


def _read() -> List[Dict[str, Any]]:
    try:
        data = json.loads(queue_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    now = time.time()
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("path"), str) and now - float(e.get("created", 0)) < MAX_AGE_S] if isinstance(data, list) else []


def _write(entries: List[Dict[str, Any]]) -> None:
    queue = queue_file()
    queue.parent.mkdir(parents=True, exist_ok=True)
    tmp = queue.with_name(".%s.%s.tmp" % (queue.name, uuid.uuid4().hex[:8]))
    tmp.write_text(json.dumps(entries[-MAX_ENTRIES:]), encoding="utf-8")
    os.replace(str(tmp), str(queue))


def push(path: str, kind: str, focus: bool = True) -> Dict[str, Any]:
    entry = {"id": uuid.uuid4().hex[:12], "path": str(path), "kind": kind, "name": os.path.basename(str(path)), "focus": bool(focus), "created": time.time()}
    entries = [e for e in _read() if e["path"] != entry["path"]] + [entry]
    _write(entries)
    return entry


def pop_all() -> List[Dict[str, Any]]:
    """Everything waiting, oldest first; the queue is empty afterwards."""
    entries = _read()
    if entries:
        _write([])
    return entries
