"""Fake-Hermes tests: register(ctx) registers 45 valid tools + 1 skill; installed copy loads under any module name."""
import importlib.util
import json
import subprocess
import sys

import pytest

from conftest import ROOT

import hermes_video_editor

EXPECTED_TOOLS = 45


class FakeCtx:
    def __init__(self):
        self.tools, self.skills = {}, {}

    def register_tool(self, name, toolset, schema, handler, override=False, check_fn=None):
        assert name not in self.tools, "duplicate tool " + name
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_skill(self, name, path):
        self.skills[name] = path


def registered():
    ctx = FakeCtx()
    hermes_video_editor.register(ctx)
    return ctx


def test_counts():
    ctx = registered()
    assert len(ctx.tools) == EXPECTED_TOOLS
    assert list(ctx.skills) == ["video-editor"]
    assert ctx.skills["video-editor"].is_file()


def check_schema(name, schema):
    assert schema["name"] == name
    assert len(schema["description"]) >= 40, name
    json.dumps(schema)                                   # serialisable
    params = schema["parameters"]
    assert params["type"] == "object" and isinstance(params["properties"], dict)
    for req in params.get("required", []):
        assert req in params["properties"], (name, req)
    for key, prop in params["properties"].items():
        assert prop.get("type"), (name, key)
        assert prop.get("description"), (name, key)
        if "enum" in prop:
            assert prop["enum"] and len(set(map(str, prop["enum"]))) == len(prop["enum"]), (name, key)
        if "default" in prop and "enum" in prop:
            assert prop["default"] in prop["enum"], (name, key)
        if prop["type"] == "array":
            assert "items" in prop, (name, key)


def test_all_schemas_valid():
    for name, tool in registered().tools.items():
        assert name.startswith("lk_") and tool["toolset"] == "video_editor"
        check_schema(name, tool["schema"])
        assert callable(tool["handler"])


def test_common_params_present():
    for name, tool in registered().tools.items():
        props = tool["schema"]["parameters"]["properties"]
        if name in ("lk_media_doctor",):
            assert "timeout_s" in props
        elif name in ("lk_media_probe", "lk_detect_silence", "lk_detect_scenes", "lk_platform_check", "lk_loudness_report"):
            assert "input" in props and "timeout_s" in props
        elif name in ("lk_join", "lk_crossfade_join"):
            assert {"output", "output_dir", "overwrite", "timeout_s"} <= set(props)
        elif name == "lk_split":      # writes several files, so no single 'output'
            assert {"input", "output_dir", "overwrite", "timeout_s"} <= set(props)
        else:
            assert {"input", "output", "output_dir", "overwrite", "timeout_s"} <= set(props), name


def test_every_tool_documented():
    docs = (ROOT / "docs" / "en" / "TOOLS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    skill = (ROOT / "skills" / "video-editor" / "SKILL.md").read_text(encoding="utf-8")
    for name in registered().tools:
        assert "`%s`" % name in docs, name + " missing in docs/en/TOOLS.md"
        assert name in skill, name + " missing in SKILL.md"
    assert str(EXPECTED_TOOLS) in readme


def test_docs_in_sync():
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_docs.py"), "--check"]).returncode == 0, \
        "docs/en/TOOLS.md is stale: run python scripts/gen_docs.py"


def test_no_forbidden_patterns():
    """No shell=True, no outbound network code, no placeholders. The editor may LISTEN on loopback (http.server)."""
    files = (list(ROOT.glob("core/*.py")) + list(ROOT.glob("tools/*.py")) + list(ROOT.glob("editor/*.py"))
             + [ROOT / "__init__.py", ROOT / "schemas.py", ROOT / "dashboard" / "plugin_api.py"])
    banned_text = ["shell=True", "TODO", "FIXME", "os.system", "eval(", "exec("]
    banned_modules = ["urllib.request", "urllib2", "requests", "http.client", "socket", "ftplib", "smtplib",
                      "telnetlib", "websocket", "aiohttp", "httpx"]
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pat in banned_text:
            assert pat not in text, (path, pat)
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                module = stripped.split()[1]
                assert module not in banned_modules and module.split(".")[0] not in banned_modules, (path, stripped)


def test_installed_plugin_loads_like_hermes(tmp_path):
    """Install via scripts/install.py (copy mode) and import under a different package name."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--target", str(tmp_path), "--copy"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    dest = tmp_path / "hermes-video-editor"
    assert (dest / "plugin.yaml").is_file() and (dest / "skills" / "video-editor" / "SKILL.md").is_file()
    assert not (dest / "tests").exists() and not (dest / ".git").exists()
    name = "hermes_plugins_video_editor_test"
    spec = importlib.util.spec_from_file_location(name, dest / "__init__.py", submodule_search_locations=[str(dest)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        ctx = FakeCtx()
        mod.register(ctx)
        assert len(ctx.tools) == EXPECTED_TOOLS and "video-editor" in ctx.skills
        assert json.loads(ctx.tools["lk_media_doctor"]["handler"]({}))["ok"] in (True, False)
    finally:
        for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
            del sys.modules[key]


def test_install_refuses_foreign_dir_and_uninstalls(tmp_path):
    foreign = tmp_path / "hermes-video-editor"
    foreign.mkdir()
    (foreign / "x.txt").write_text("mine")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--target", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and (foreign / "x.txt").exists()
    foreign.rename(tmp_path / "old")
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--target", str(tmp_path)],
                          capture_output=True).returncode == 0
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "install.py"), "--target", str(tmp_path),
                           "--uninstall"], capture_output=True).returncode == 0
    assert not (tmp_path / "hermes-video-editor").exists()


def test_install_in_place_never_deletes_itself(tmp_path):
    """Regression: running install.py from inside ~/.hermes/plugins/<name> (a git clone) used to delete the folder
    and leave a self-referencing symlink."""
    import shutil
    plugins = tmp_path / "plugins"
    shutil.copytree(str(ROOT), str(plugins / "hermes-video-editor"),
                    ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "tests"))
    inside = plugins / "hermes-video-editor"
    script = inside / "scripts" / "install.py"
    r = subprocess.run([sys.executable, str(script), "--target", str(plugins)], capture_output=True, text=True, cwd=str(inside))
    assert r.returncode == 0, r.stderr
    assert inside.is_dir() and not inside.is_symlink() and (inside / "plugin.yaml").is_file()
    assert (tmp_path / "desktop-plugins" / "hermes-video-editor" / "plugin.js").is_file()
    again = subprocess.run([sys.executable, str(script), "--target", str(plugins), "--uninstall"], capture_output=True, text=True)
    assert again.returncode == 0 and (inside / "plugin.yaml").is_file()          # refuses to delete itself
