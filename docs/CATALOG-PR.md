# Catalog submission checklist (NousResearch/hermes-agent)

1. The repository must be public and the commit you pin must be on its default branch.
2. `python scripts/make_catalog_entry.py <merged-sha> > plugin-catalog/hermes-video-editor.yaml` (pins the SHA; the banner and screenshot URLs contain it).
3. `hermes plugins validate . --install-deps` must pass (capabilities match the code, no `dangerous` findings).
4. Open a PR to `NousResearch/hermes-agent` adding only that file. Suggested PR text below.

## PR text

**Add hermes-video-editor (community, tools)**

Local video editor for your own footage: 45 FFmpeg tools for the agent plus a visual editor page in Hermes Desktop
(canvas, overlay track, text, music, English/German help). Licence: PolyForm Noncommercial 1.0.0 (source-available, non-commercial use).

Disclosure (also in the README, section "Security and disclosures"):

- Runs `ffmpeg` / `ffprobe` as subprocesses (argument lists, `shell=False`) on files the user names; writes new files, never modifies inputs.
- The editor page starts a local HTTP listener on `127.0.0.1` (random port, one-time token, Host header checked, access limited to media files below the home folder). It stops with the process.
- Caches low-res previews, waveforms and thumbnails in the system temp folder.
- No outbound network access, no telemetry, no downloads, no credentials, no hooks, no core overrides.
- Desktop page: public SDK only (`@hermes/plugin-sdk`, `react`), no `eval`, no lookups in the app's own UI or style sheets. It reads the theme through `getComputedStyle` on its own container and an `attributes` MutationObserver on the document root to follow light/dark changes.
- Optional `lk_transcribe_captions` uses `faster-whisper` only if the user installed it and a model is already on disk.

Capabilities declared in `plugin.yaml` are generated from the registrations and checked by a test.
