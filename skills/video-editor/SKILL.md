---
name: video-editor
description: Edit the user's OWN local video/audio files with FFmpeg (ve_* tools). Use for trimming, cutting silence, cropping to 9:16, captions, music, loudness, export presets and platform checks. 100% local - never promise cloud features.
---

# Video Editor (local FFmpeg)

You edit **the user's own footage on their machine**. There is no cloud, no AI video generation,
no stock library, no upload. If the user wants something that needs those, say so plainly.

## The 6 rules

1. **Probe first.** Call `ve_media_probe` on every new input before you edit. It tells you
   duration, size, fps, rotation and whether there is audio.
2. **One tool per step.** Chain tools. The `output` of one step is the `input` of the next.
3. **Inputs are never changed.** Each tool writes a NEW file (`<name>_<op>.<ext>`). Tell the
   user where the final file is.
4. **Check `ok`.** If `ok` is false read `error` and `hint`, fix the cause, retry once. Do not
   loop blindly. If ffmpeg is missing run `ve_media_doctor` and show the install hint.
5. **Social clips end with `ve_platform_check`.** Apply the `fixes` it returns, then re-check.
6. **Be honest about limits** (see the end).

## Units and formats

- Times: seconds (`12.5`), `MM:SS` or `HH:MM:SS(.ms)`.
- Sizes: pixels. Loudness: LUFS. Gain: dB.
- Silent clips (no audio stream) are fine. Audio tools reject them with a clear error: skip them.

## Which tool for what

| Goal | Tool |
|---|---|
| Look at a file | `ve_media_probe`, `ve_contact_sheet`, `ve_extract_frame` |
| Find things | `ve_detect_silence`, `ve_detect_scenes` |
| Keep a section | `ve_trim` |
| Cut into parts / join | `ve_split`, `ve_join` |
| Delete middle sections | `ve_remove_segments`, `ve_remove_silence` |
| Speed / reverse / loop | `ve_change_speed`, `ve_reverse`, `ve_loop` |
| Crop / resize / rotate | `ve_crop`, `ve_crop_to_aspect`, `ve_resize`, `ve_rotate_flip` |
| Vertical without losing picture | `ve_pad_blur_background` |
| Look | `ve_color_adjust`, `ve_denoise_video`, `ve_fade_video`, `ve_stabilize` |
| Text and graphics | `ve_add_text`, `ve_burn_captions`, `ve_add_image_overlay` |
| Two videos | `ve_picture_in_picture`, `ve_stack_videos` |
| Hide something | `ve_blur_region` (fixed box, no tracking) |
| Sound | `ve_extract_audio`, `ve_replace_audio`, `ve_mix_music`, `ve_normalize_loudness`, `ve_sync_audio_offset`, `ve_adjust_volume`, `ve_fade_audio`, `ve_denoise_audio` |
| Deliver | `ve_export_preset`, `ve_platform_check`, `ve_compress_to_size`, `ve_to_gif` |
| Speech to subtitles (optional) | `ve_transcribe_captions` |

## Recipes

### A. Reel / TikTok / Short from a landscape clip
1. `ve_media_probe`
2. Choose ONE:
   - Lose the sides, fill the screen: `ve_crop_to_aspect` `aspect=9:16` (`anchor` = where the subject is).
   - Keep everything, blurred bars: `ve_pad_blur_background` (1080x1920).
3. Optional: `ve_remove_silence`, `ve_add_text` (hook in the first seconds), `ve_normalize_loudness` (-14).
4. Captions (if wanted): `ve_transcribe_captions` -> `ve_burn_captions` with `reels_safe=true`.
5. `ve_export_preset` `preset=reels` (or `tiktok` / `shorts`).
6. `ve_platform_check` with the same platform. Fix what fails, re-check.

### B. Tighten a talking-head video
1. `ve_media_probe` (needs audio)
2. `ve_detect_silence` to preview, then `ve_remove_silence` (defaults: -35 dB, 0.5 s, 0.1 s padding;
   if it cuts speech, lower `noise_db` to -45 or raise `min_silence_s`).
3. `ve_denoise_audio` `preset=voice` if there is hiss.
4. `ve_transcribe_captions` -> `ve_burn_captions`.
5. `ve_normalize_loudness` (-14 for social, -16 for podcasts/YouTube talks).
6. `ve_export_preset` `youtube_1080p` -> `ve_platform_check`.

### C. Podcast / voice clip with background music (ducking)
1. `ve_trim` to the wanted section.
2. `ve_denoise_audio` `voice`, then `ve_mix_music` (`ducking=true`, `music_volume_db=-18`; music dips while speaking).
3. `ve_normalize_loudness` last (it measures the final mix).
4. Audio only wanted? `ve_extract_audio` (mp3/m4a/wav/flac).

### D. Shrink for Discord / email
1. `ve_media_probe` (duration decides what is realistic).
2. `ve_export_preset` `preset=discord_8mb`, or `ve_compress_to_size` `target_mb=...`.
3. Too long for the budget? `ve_trim` first, or `ve_change_speed`. Say honestly if quality will suffer.
4. `ve_platform_check` `platform=discord_8mb`.

## Gotchas

- `ve_trim` `mode=fast` is instant but snaps to keyframes; use default `accurate` for exact cuts.
- `ve_blur_region` does NOT follow moving objects. Say so; offer a time window instead.
- `ve_stabilize` is basic (deshake). Do not promise gimbal quality.
- `ve_burn_captions` burns text into the picture. Give the user the `.srt` too if they may edit it.
- `ve_transcribe_captions` needs `pip install faster-whisper` and a local model. If it returns
  `ok:false`, relay the hint; never try to download models yourself.
- Platform limits in `ve_platform_check` are editable defaults and can be outdated. Say "according
  to the plugin's rules, verify current limits" for borderline cases.
- Long jobs: raise `timeout_s` (default 600) for big files instead of retrying.

## Never

- Never claim cloud rendering, AI generation, stock footage, auto-upload or posting to platforms.
- Never overwrite the user's original; do not pass the input path as `output`.
- Never invent file paths. Use the `output` value from the previous result.
