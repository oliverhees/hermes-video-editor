import subprocess
import sys
from pathlib import Path

from conftest import ROOT, TOOLS


def parse_lists(text):
    """Tiny YAML reader for our manifest: top-level scalars + (nested) string lists."""
    data, section, sub = {}, None, None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if line.startswith("- "):
            (data[section][sub] if sub else data[section]).append(line[2:])
        elif ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            if indent == 0:
                section, sub = key, None
                data[key] = [] if val == "" else ({} if False else val)
                if val == "":
                    data[key] = []
            else:
                if isinstance(data[section], list):
                    data[section] = {}
                sub = key
                data[section][key] = [] if val in ("", "[]") else val
    return data


def test_manifest_matches_registrations():
    m = parse_lists((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    names = [t["name"] for t in TOOLS]
    assert m["provides_tools"] == names
    caps = m["capabilities"]
    assert caps["provides_tools"] == names
    assert caps["provides_hooks"] == [] and caps["provides_middleware"] == [] and caps["requires_env"] == []
    assert m["name"] == "hermes-video-editor" and m["version"] == '"0.1.0"'


def test_manifest_script_in_sync():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_manifest.py"), "--check"])
    assert r.returncode == 0, "plugin.yaml is stale: run python scripts/sync_manifest.py"
