---
name: video-editor
description: Edit the user's OWN local video/audio files with FFmpeg (lk_* tools). Use for trimming, cutting silence, cropping to 9:16, captions, music, loudness, export presets and platform checks. 100% local - never promise cloud features.
---

# Video Editor (local FFmpeg)

You edit **the user's own footage on their machine**. There is no cloud, no AI video generation,
no stock library, no upload. If the user wants something that needs those, say so plainly.

## The 6 rules

1. **Probe first.** Call `lk_media_probe` on every new input before you edit. It tells you
   duration, size, fps, rotation and whether there is audio.
2. **One tool per step.** Chain tools. The `output` of one step is the `input` of the next.
3. **Inputs are never changed.** Each tool writes a NEW file (`<name>_<op>.<ext>`). Tell the
   user where the final file is.
4. **Check `ok`.** If `ok` is false read `error` and `hint`, fix the cause, retry once. Do not
   loop blindly. If ffmpeg is missing run `lk_media_doctor` and show the install hint.
5. **Social clips end with `lk_platform_check`.** Apply the `fixes` it returns, then re-check.
6. **Be honest about limits** (see the end).

## The visual editor (for the user, not for you)

Besides your tools the plugin has a visual cut editor: sidebar entry **Video Editor** in Hermes Desktop (or
`python scripts/editor.py` in a browser). The user can mark cuts, find silences, reframe, place clips on a canvas, add text and a music track, and export there by clicking.
Point them to it when they want to scrub, preview or fine-tune cuts by eye; you cannot operate it yourself.
Files the user exports there appear as new files next to the original.

## Units and formats

- Times: seconds (`12.5`), `MM:SS` or `HH:MM:SS(.ms)`.
- Sizes: pixels. Loudness: LUFS. Gain: dB.
- Silent clips (no audio stream) are fine. Audio tools reject them with a clear error: skip them.

## Which tool for what

| Goal | Tool |
|---|---|
| Look at a file | `lk_media_probe`, `lk_contact_sheet`, `lk_extract_frame` |
| Find things | `lk_detect_silence`, `lk_detect_scenes` |
| Keep a section | `lk_trim` |
| Cut into parts / join | `lk_split`, `lk_join` |
| Delete middle sections | `lk_remove_segments`, `lk_remove_silence` |
| Speed / reverse / loop | `lk_change_speed`, `lk_reverse`, `lk_loop` |
| Crop / resize / rotate | `lk_crop`, `lk_crop_to_aspect`, `lk_resize`, `lk_rotate_flip` |
| Vertical without losing picture | `lk_pad_blur_background` |
| Look | `lk_color_adjust`, `lk_denoise_video`, `lk_fade_video`, `lk_stabilize` |
| Text and graphics | `lk_add_text`, `lk_burn_captions`, `lk_add_image_overlay` |
| Two videos | `lk_picture_in_picture`, `lk_stack_videos` |
| Hide something | `lk_blur_region` (fixed box, no tracking) |
| Sound | `lk_extract_audio`, `lk_replace_audio`, `lk_mix_music`, `lk_normalize_loudness`, `lk_sync_audio_offset`, `lk_adjust_volume`, `lk_fade_audio`, `lk_denoise_audio` |
| Deliver | `lk_export_preset`, `lk_platform_check`, `lk_compress_to_size`, `lk_to_gif` |
| Speech to subtitles (optional) | `lk_transcribe_captions` |

## Recipes

### A. Reel / TikTok / Short from a landscape clip
1. `lk_media_probe`
2. Choose ONE:
   - Lose the sides, fill the screen: `lk_crop_to_aspect` `aspect=9:16` (`anchor` = where the subject is).
   - Keep everything, blurred bars: `lk_pad_blur_background` (1080x1920).
3. Optional: `lk_remove_silence`, `lk_add_text` (hook in the first seconds), `lk_normalize_loudness` (-14).
4. Captions (if wanted): `lk_transcribe_captions` -> `lk_burn_captions` with `reels_safe=true`.
5. `lk_export_preset` `preset=reels` (or `tiktok` / `shorts`).
6. `lk_platform_check` with the same platform. Fix what fails, re-check.

### B. Tighten a talking-head video
1. `lk_media_probe` (needs audio)
2. `lk_detect_silence` to preview, then `lk_remove_silence` (defaults: -35 dB, 0.5 s, 0.1 s padding;
   if it cuts speech, lower `noise_db` to -45 or raise `min_silence_s`).
3. `lk_denoise_audio` `preset=voice` if there is hiss.
4. `lk_transcribe_captions` -> `lk_burn_captions`.
5. `lk_normalize_loudness` (-14 for social, -16 for podcasts/YouTube talks).
6. `lk_export_preset` `youtube_1080p` -> `lk_platform_check`.

### C. Podcast / voice clip with background music (ducking)
1. `lk_trim` to the wanted section.
2. `lk_denoise_audio` `voice`, then `lk_mix_music` (`ducking=true`, `music_volume_db=-18`; music dips while speaking).
3. `lk_normalize_loudness` last (it measures the final mix).
4. Audio only wanted? `lk_extract_audio` (mp3/m4a/wav/flac).

### D. Shrink for Discord / email
1. `lk_media_probe` (duration decides what is realistic).
2. `lk_export_preset` `preset=discord_8mb`, or `lk_compress_to_size` `target_mb=...`.
3. Too long for the budget? `lk_trim` first, or `lk_change_speed`. Say honestly if quality will suffer.
4. `lk_platform_check` `platform=discord_8mb`.

## Gotchas

- `lk_trim` `mode=fast` is instant but snaps to keyframes; use default `accurate` for exact cuts.
- `lk_blur_region` does NOT follow moving objects. Say so; offer a time window instead.
- `lk_stabilize` is basic (deshake). Do not promise gimbal quality.
- `lk_burn_captions` burns text into the picture. Give the user the `.srt` too if they may edit it.
- `lk_transcribe_captions` needs `pip install faster-whisper` and a local model. If it returns
  `ok:false`, relay the hint; never try to download models yourself.
- Platform limits in `lk_platform_check` are editable defaults and can be outdated. Say "according
  to the plugin's rules, verify current limits" for borderline cases.
- Long jobs: raise `timeout_s` (default 600) for big files instead of retrying.

## Never

- Never claim cloud rendering, AI generation, stock footage, auto-upload or posting to platforms.
- Never overwrite the user's original; do not pass the input path as `output`.
- Never invent file paths. Use the `output` value from the previous result.
