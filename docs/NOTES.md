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
