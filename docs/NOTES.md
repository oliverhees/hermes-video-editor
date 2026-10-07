# Phase 0: Research notes (Hermes plugin API)

Sources read: user-guide/features/plugins, developer-guide/plugins/index,
spider-rs/hermes-plugins (layout + smoke test).
Not reachable: `website/docs/guides/build-a-hermes-plugin.md` (HTTP 404 on both
github.com and raw.githubusercontent.com, path moved or renamed). Its content is
covered by the two other docs.

## plugin.yaml
Required: `name`, `version`, `description`.
Optional: `provides_tools` (list), `provides_hooks`, `author`, `license`,
`homepage`, `requires_env`, `capabilities`, `python_dependencies`,
`config_schema`, `manifest_version`, `api_version`, `requires_plugins`.
`capabilities` are privileged surfaces needing consent (`tools.override`,
`llm.model_override`, `gateway.platform_actions`). We need NONE.

## ctx.register_tool
```python
ctx.register_tool(name=..., toolset=..., schema={name, description, parameters},
                  handler=fn, override=False, check_fn=None)
```
`schema` is the full object: `"name"`, `"description"`, `"parameters"`
(`{"type":"object","properties":...}`). `check_fn` can gate availability.

## Handler
`def handler(args: dict, **kwargs) -> str`: returns a JSON string, never raises,
accepts `**kwargs` (task_id, session_id, ...).

## Skills
`ctx.register_skill(name, path_to_SKILL_md)`; exposed as `plugin:name`,
loaded via `skill_view("plugin:name")`. Plugin layout has `skills/<name>/SKILL.md`.

## CLI
`hermes plugins list | enable <name> | disable <name> | install owner/repo [--enable]
| remove <name> | update <name> | doctor [path] --ci`
Plugins live in `~/.hermes/plugins/<name>/` (project-local `.hermes/plugins/`
needs `HERMES_ENABLE_PROJECT_PLUGINS=true`). Plugins are opt-in: must be enabled.

## Differences from the master prompt's assumptions
1. Handler signature is `(args: dict, **kwargs)`, a dict plus kwargs, not `**params`.
2. `schema` passed to `register_tool` must contain `name`, `description`, `parameters`
   (not just a parameters block).
3. `register_tool` has extra optional `override`/`check_fn` (unused, except
   `check_fn` is a candidate for ffmpeg availability; we keep tools always listed
   and return a JSON error instead, as requested).
4. `provides_tools` is a plain list of names; we generate it from the TOOLS table.
5. Extra useful command: `hermes plugins doctor <path> --ci` for validation.
6. Guide page 404: unverified, nothing relied on from it.

## Addendum: plugin catalog rules (from `plugin-catalog/README.md` and the catalog-submission guide)

- `plugin.yaml` should carry a `capabilities:` block (`provides_tools`, `provides_hooks`, `provides_middleware`,
  `requires_env`) that MUST match what `register()` registers. We generate it (`scripts/sync_manifest.py`) and a test
  compares it with the real TOOLS table. Top-level `provides_tools` is kept too (developer guide).
- Validation command: `hermes plugins validate <path> --install-deps` (checks manifest, loading, capability match,
  security scan). Hermes is not installed in this sandbox, so it could not be run here; `hermes plugins doctor <path> --ci`
  from the developer guide is the older name. Run whichever your Hermes version has.
- Catalog entry = one file `plugin-catalog/<name>.yaml` in NousResearch/hermes-agent: `name`, `repo` (https), `sha`
  (full 40 chars, mandatory), `version` (quoted), `description`, `maintainer`, `category`, `requires_hermes` (SemVer floor,
  never newer than the current release), `capabilities`. `scripts/make_catalog_entry.py` prints it for HEAD.
- Admission rules we satisfy: pinned SHA only, no self-updating code, public `register_*` surfaces only, no core overrides,
  credentials only via `requires_env` (none), risky behaviour disclosed (subprocess ffmpeg; see README "Security").
- Open item: the exact current Hermes release number for `requires_hermes` is unverified (`>=0.21.5` is the docs' example).

## Addendum: Desktop plugin surface (from `desktop-plugin-sdk.md`, `extending-the-dashboard.md`)

- Unified package: `plugin.yaml` + `dashboard/manifest.json` (`{"name": id, "api": "plugin_api.py"}`) +
  `dashboard/plugin_api.py` (FastAPI `router`, mounted at `/api/plugins/<id>/`) + `desktop/plugin.js`.
  Folder name, `plugin.yaml` name and the exported `id` must match. Installing copies `desktop/plugin.js` to
  `$HERMES_HOME/desktop-plugins/<id>/`; `scripts/install.py` does the same for symlink installs.
- Desktop JS: single ESM file, only `@hermes/plugin-sdk` and `react` imports, no JSX. We use `ROUTES_AREA` +
  `SIDEBAR_NAV_AREA` (`registerMany`), `ctx.rest('/start')` and `SandboxedFrame`.
- `SandboxedFrame`: absolute `http(s):` or `data:` `src` only, opaque origin, sandbox tokens limited to
  `allow-scripts allow-forms allow-downloads ...` (no `allow-same-origin`, no `srcdoc`). No raw `<video>` and no file
  pickers in the plugin itself, so the editor page runs inside the frame and talks to its own loopback server.
  Consequence: the server must send CORS headers and cannot use cookies or localStorage (guarded with try/catch).
- Unknowns (not in the docs I could read): whether the Desktop app restricts `frame-src` to loopback URLs, and how a
  plugin can learn the gateway's base URL (we do not need it: `/start` returns our own URL).
- Verified here with headless Chromium against the real server; **not** verified inside the real Desktop app.
