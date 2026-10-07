# hermes-video-editor

> Powered by [Lokyy.de](https://lokyy.de) - German Hermes Engineering

**Edit your OWN local videos from chat.** A plugin for [Hermes Agent](https://hermes-agent.nousresearch.com/)
with **42 FFmpeg tools**. 100% local: no cloud, no API key, no network calls, no telemetry.

> Not "generate me a video". It is "cut / crop / caption / master **my** footage".

![Video Editor](docs/banner.png)

## TL;DR

- 42 tools, all prefixed `ve_` (`ve_trim`, `ve_crop_to_aspect`, `ve_burn_captions`, ...)
- Needs only **FFmpeg + ffprobe** on your PATH and Python 3.9+. No pip packages for the core.
- Never touches your original file. Results are new files: `<name>_<op>.<ext>`.
- Ships a skill that teaches the agent the right order of steps (probe first, platform check last).
- Ships a **visual cut editor** (sidebar entry "Video Editor" in Hermes Desktop, or standalone in any browser).

## Install (3 steps)

1. **Install FFmpeg**

   | OS | Command |
   |---|---|
   | Linux | `apt install ffmpeg` (with admin rights) |
   | macOS | `brew install ffmpeg` |
   | Windows | `winget install Gyan.FFmpeg` |

2. **Install the plugin**

   ```bash
   git clone https://github.com/oliverhees/hermes-video-editor
   cd hermes-video-editor
   python scripts/install.py        # symlink (Linux/macOS) or copy (Windows) into ~/.hermes/plugins
                                    # and copies the Desktop page to ~/.hermes/desktop-plugins/
   ```

   Or directly from Git: `hermes plugins install oliverhees/hermes-video-editor`

3. **Enable and check**

   ```bash
   hermes plugins enable hermes-video-editor
   hermes plugins list
   ```

   Restart Hermes. Then ask: *"Run ve_media_doctor"* - it reports FFmpeg version, encoders and filters.

Uninstall: `python scripts/install.py --uninstall`.

## The visual editor

![Editor screenshot](docs/editor.png)

*(Real screenshot of the editor; the demo clip is a synthetic test video.)*

Open **Video Editor** in the Hermes Desktop sidebar (enable the plugin under *Capabilities -> Plugins* if it is off),
or run it on its own in any browser:

```bash
python scripts/editor.py                 # prints a link and opens your browser
python scripts/editor.py my-video.mp4    # with a file preloaded
```

| Do this | How |
|---|---|
| Add a video | **Add clip...** (browse your home folder or paste a path), pick one from **Recent**, or **drop video files** into the window. Several files can be dropped at once; they are appended in order (dropped files are copied into the editor's cache; exports then go to `~/Videos` by default) |
| Preview | Space = play/pause (plays across clips without gaps), arrows = frame step, Shift+arrows = 1 s, Up/Down = previous/next clip boundary |
| Split | Put the playhead where you want the cut, press `S` |
| Delete a clip | Click it, press `Delete` (the gap closes automatically) |
| Remove a range | `I` (in), `O` (out), `X` (cut), or Shift+drag on the timeline. Works across clip borders |
| Reorder | Drag a clip to another position (an orange line shows where it lands) |
| Trim | Drag the left or right edge of a clip |
| Undo / redo | `Ctrl+Z` / `Ctrl+Shift+Z` (100 steps) |
| Remove silences | *Edit* tab -> **Remove silences** (selected clip, or all clips if none is selected) |
| Several videos in one | Just add more clips; different sizes, frame rates and audio formats are matched on export (black bars, silence for clips without sound) |
| Save / open a project | **Save** / **Save as...** / **Open project...** (a `.vproj.json` file that remembers clips and cut points, not the media) |
| **Canvas** (16:9, 9:16, 1:1, 4:5, or auto) and resolution | *Picture* tab. The preview shows the canvas; the output has exactly that size |
| **Background** behind pictures that do not fill the canvas | *Picture* tab: blurred copy of the picture, black, or a colour |
| **Position and size of each clip** | Select a clip, then drag the picture on the preview, drag a corner or use the mouse wheel to zoom; or use the sliders and **Fit / Fill / Center / Reset**. Split a clip first to place each part differently (e.g. re-frame when the speaker moves). Fill makes a 16:9 clip cover a 9:16 canvas |
| Speed | *Picture* tab. Applied to the whole timeline on export |
| Loudness | *Sound* tab |
| **Any of the 42 tools** | *All tools* tab: every `ve_*` tool as a form (search, fill in, Run). Results can be added to the timeline |
| Export | *Export* tab: pick a platform preset, then **Export**. The timeline is rendered first, then speed/format/loudness/preset are applied, then a platform check is shown |

The editor never changes your original. **Export** runs the same `ve_*` tools the agent uses
(remove cuts -> speed -> reframe -> loudness -> preset) and writes a new file next to the original (or into the folder you choose).
It is an *assembly* editor: one video track of clips played back to back, each with its own position and size on a canvas. Layers (overlays, text, music tracks) are planned; picture-in-picture, stacking and text overlays are available as tools in the *All tools* tab.

How it works and what it exposes: a tiny web server inside the plugin listens on **127.0.0.1 only** (random port, random
one-time token in the link; requests without it get 403).
The page follows the app theme (light/dark and accent colour are read from Hermes Desktop; standalone it follows your system theme). It serves the editor page, streams the video you open
and runs the tools. It only reads/writes **media files below your home folder** (add more with the `VE_EDITOR_ROOTS`
environment variable, separated by `:` or `;` on Windows). Nothing leaves your machine.

## Or just talk to Hermes: 5 examples

1. **Look first**: *"Probe `~/Videos/interview.mp4` and show me a contact sheet."*
2. **Tighten a talking head**: *"Remove the silences from `interview.mp4`, normalise to -14 LUFS, burn captions."*
   (`ve_remove_silence` -> `ve_transcribe_captions` -> `ve_burn_captions` -> `ve_normalize_loudness`)
3. **Reel from a landscape clip**: *"Make a Reel from `trip.mp4`: 9:16 with blurred background, add the title 'Day 3', export for Reels and check it."*
   (`ve_pad_blur_background` -> `ve_add_text` -> `ve_export_preset reels` -> `ve_platform_check`)
4. **Music under a voice clip**: *"Trim 00:12 to 01:05 of `podcast.mp4` and put `lofi.mp3` quietly underneath, ducking while I talk."*
5. **Shrink for Discord**: *"Make `clip.mp4` fit under 8 MB."* (`ve_export_preset discord_8mb` or `ve_compress_to_size`)

## What you get (42 tools)

| Group | Tools |
|---|---|
| **A. Inspect (5)** | `ve_media_doctor` `ve_media_probe` `ve_detect_silence` `ve_detect_scenes` `ve_extract_frame` |
| **B. Cut & time (8)** | `ve_trim` `ve_split` `ve_join` `ve_remove_silence` `ve_remove_segments` `ve_change_speed` `ve_reverse` `ve_loop` |
| **C. Picture (9)** | `ve_crop` `ve_crop_to_aspect` `ve_resize` `ve_rotate_flip` `ve_pad_blur_background` `ve_color_adjust` `ve_denoise_video` `ve_fade_video` `ve_stabilize` |
| **D. Overlays & text (6)** | `ve_add_text` `ve_burn_captions` `ve_add_image_overlay` `ve_picture_in_picture` `ve_stack_videos` `ve_blur_region` |
| **E. Audio (8)** | `ve_extract_audio` `ve_replace_audio` `ve_mix_music` `ve_normalize_loudness` `ve_sync_audio_offset` `ve_adjust_volume` `ve_fade_audio` `ve_denoise_audio` |
| **F. Export & check (6)** | `ve_export_preset` `ve_platform_check` `ve_compress_to_size` `ve_to_gif` `ve_contact_sheet` `ve_transcribe_captions` |

Full parameter reference: [docs/TOOLS.md](docs/TOOLS.md) (generated from the schemas).

## How every tool behaves

- **Result**: a JSON string.
  Success: `{"ok": true, "output": "<path>", "duration_s": <seconds of the OUTPUT>, "info": {...}}`.
  Failure: `{"ok": false, "error": "...", "hint": "...", "ffmpeg_stderr_tail": "..."}`. Tools never raise.
- **Output names**: `<input name>_<op>.<ext>` next to the input, or in `output_dir`, or exactly `output`.
  If it exists you get `_1`, `_2`, ... unless `overwrite=true`. The input file is never an allowed output.
- **Times**: `12.5`, `01:30` or `00:01:30.250`. **Timeout**: `timeout_s` (default 600); FFmpeg is killed when it expires.
- **Silent clips** and **odd sizes** are handled (odd sizes are rounded down to even for H.264).
- **Paths** with spaces and umlauts work (arguments are passed as lists; no shell is ever used).

## Fonts for text

`ve_add_text` needs a font file. Order: `font_file` parameter, `VE_FONT` environment variable, then per OS
Linux: DejaVu Sans / Liberation Sans, macOS: Helvetica / Arial, Windows: `arial.ttf`. If none is found FFmpeg's
default (fontconfig) is used. `ve_media_doctor` shows which font was picked. `ve_burn_captions` uses libass
and your system fonts (`font_name`).

## Platform rules

`ve_platform_check` compares a file with limits in [`platform_rules.py`](platform_rules.py) (one editable dict).
**Verify current platform limits**: platforms change them without notice; edit the dict when they do.

## Optional: captions from speech

```bash
pip install faster-whisper
python -c "from faster_whisper import WhisperModel; WhisperModel('base')"   # one-time model download, done by YOU
```

`ve_transcribe_captions` only uses models already on disk (`local_files_only`); the plugin itself never
downloads anything. Without the package the tool answers `ok:false` with this hint and nothing else breaks.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg not found on PATH` | Install FFmpeg (table above), restart Hermes/terminal, run `ve_media_doctor`. |
| `no 'drawtext' / 'subtitles' filter` | Your FFmpeg build lacks freetype/libass. Install a full build (Windows: Gyan "full"). |
| `Not a readable media file` | File is corrupt, still being written, or not media. Probe it first. |
| Text is missing / tofu boxes | Pass `font_file` with a font that has your characters, or set `VE_FONT`. |
| Captions too low in Reels | Use `reels_safe=true` or raise `bottom_margin_px`. |
| `timed out` | Raise `timeout_s` for big files. |
| `Could not reach X MB` | Target too small for the length: shorten the clip, raise `target_mb`. |
| `ve_reverse` refuses | It needs the whole clip in RAM (limit 300 s): `ve_trim` first. |
| No "Video Editor" in the sidebar | Enable it under *Capabilities -> Plugins*, make sure you are in the right Hermes profile, restart the app. Check `~/.hermes/desktop-plugins/hermes-video-editor/plugin.js` exists (`python scripts/install.py`). |
| Editor page says "could not start" | `hermes plugins list` must show the plugin enabled. As a fallback run `python scripts/editor.py` and open the link in a browser. |
| Editor: "Preview unavailable" | The preview needs H.264 or VP8 support. Editing and export still work. |
| Plugin not listed | `hermes plugins list`, then `hermes plugins enable hermes-video-editor`, restart Hermes. |
| Windows: install copies instead of linking | Normal without developer mode. Re-run `scripts/install.py` after `git pull`. |

## Development

```bash
python -m pip install pytest
python -m pytest -q                  # needs ffmpeg; builds tiny synthetic media, no real footage
python scripts/sync_manifest.py      # regenerate plugin.yaml after adding/removing a tool
python scripts/gen_docs.py           # regenerate docs/TOOLS.md
```

Layout: `core/` (FFmpeg runner, paths, time parsing, results), `tools/` (one module per group),
`schemas.py` (the single `TOOLS` table), `skills/video-editor/SKILL.md`, `editor/` (local server + web UI),
`dashboard/` (backend route for the Desktop page), `desktop/` (Desktop page), `tests/`, `docs/`.
Optional dev extras for the full test run: `pip install fastapi httpx playwright` (those tests skip when missing).
Regenerate the images with `python scripts/make_screenshot.py && python scripts/make_banner.py` (needs Pillow, Playwright).
CI runs on Ubuntu, macOS and Windows (`.github/workflows/test.yml`).

## Security and disclosures

- Runs `ffmpeg` / `ffprobe` as subprocesses with argument lists (`shell=False`), only on files you name.
- No outbound network access, no telemetry, no self-updating, no downloads, no credentials read, no hooks,
  no core overrides. Agent side uses only `register_tool` and `register_skill`.
- The visual editor starts a **local listener on 127.0.0.1** (random port, one-time token, Host header checked,
  CORS open only because the sandboxed frame has an opaque origin, access limited to media files below your home
  folder). It is started on demand by the Desktop page or `scripts/editor.py` and stops with the process.
- Caches previews (low-res proxy, waveform, thumbnails) in the system temp folder under `hermes-video-editor-cache`.
- Reads your input files and writes new files (outputs, plus short-lived temp files in the system temp folder).
- Declared capabilities in `plugin.yaml` are generated from the real registrations and checked by a test.

## Catalog submission (rich plugin card in Hermes Desktop)

The banner, "Repository" / "Documentation" links, "Requires Hermes" and "Reviewed commit" you see on official cards
come from a catalog entry, not from the plugin itself. To get the same card:

1. Push your commit, then `python scripts/make_catalog_entry.py` (pins the commit SHA and the banner URL).
2. `hermes plugins validate . --install-deps`
3. Open a PR to `NousResearch/hermes-agent` adding that output as `plugin-catalog/hermes-video-editor.yaml`.

The banner is `docs/banner.png` (2:1, built around a real screenshot of the editor).
Until the entry is merged the card shows the manifest description and a "Git" badge.

## Credits

Powered by [Lokyy.de](https://lokyy.de) - German Hermes Engineering. The credit is also shown at the bottom of the editor's side panel.

## License

MIT, see [LICENSE](LICENSE).
