# Video Editor: user guide

Everything runs on your computer with FFmpeg. No account, no cloud, no API key.

## 1. Start in 3 steps

1. Open **Video Editor** in the Hermes Desktop sidebar (or run `python scripts/editor.py` for a browser).
2. **Drop your videos** into the window, or click **Add clip...**
3. Cut, place, add text and music, then open the **Export** tab.

The editor never changes your original files. Every export creates a new file.

## 2. The window

| Area | What it is |
|---|---|
| Left | Tabs: **Edit, Picture, Text, Overlay, Sound, Tools, Export** |
| Centre | Preview of your canvas. Drag the picture, text or overlay right here |
| Bottom | Timeline: clips, waveform, **Text** lane, **Audio** lane, **Overlay** lane |

## 3. Cut (tab Edit)

| Do this | How |
|---|---|
| Split a clip | Put the playhead where you want the cut, press **S** |
| Delete a clip (gap closes) | Select it, press **Delete** |
| Remove a range | **I** sets the start, **O** the end, **X** removes it and closes the gap. Or hold Shift and drag on the timeline |
| Re-order clips | Drag a clip left or right |
| Trim a clip | Drag its left or right edge |
| Remove all silences | Set the level and shortest silence, click **Remove silences** (on the selected clip, or on all) |
| Undo / redo | **Ctrl+Z** / **Ctrl+Shift+Z** |

## 4. Picture (tab Picture)

- **Canvas**: 16:9, 9:16, 1:1, 4:5 or auto, plus the resolution. The output has exactly this size.
- **Background** behind pictures that do not fill the canvas: blurred copy, black or a colour.
- **Position and size of each clip**: select a clip, then drag it in the preview, use the mouse wheel, or the sliders and **Fit / Fill / Center / Reset**.
  Split a clip first to place each part differently (for example when the speaker moves).
  **Fill** makes a 16:9 clip cover a 9:16 canvas.

## 5. Video on top (tab Overlay)

A second video track above the main picture: reaction clip, logo animation, b-roll.

1. Move the playhead, open the **Overlay** tab, click **Add a video on top...**
2. Drag it in the preview to place it. Mouse wheel or the **Size** slider scales it.
   Corner buttons snap it to a corner, **Full picture** covers the canvas.
3. On the **Overlay** lane: drag to move it in time, drag the edges to trim.
4. **Opacity** blends it. **Play its sound** mixes the overlay's own audio in (off by default).

## 6. Text (tab Text)

1. Move the playhead and click **Add text at the playhead**, then type.
2. Size, colour, outline and box. Presets: **Title, Lower third, Caption**.
3. Drag the text in the preview. On the **Text** lane drag it to move, drag its edges to change how long it is visible.

## 7. Sound (tab Sound)

- **Audio track** (music, voice-over): **Add audio...** takes any audio file (or a video with sound).
  Set volume (dB), fade in/out and start time. **Ducking** lowers the music while the video speaks.
- **Loudness**: normalise to EBU R128 (-14 LUFS suits Reels, TikTok, Shorts and YouTube).
- Recording a voice-over inside the editor is not possible (the app frame has no microphone). Record a file and add it.

## 8. Export and projects (tab Export)

- Choose a **preset** (Reels, TikTok, Shorts, YouTube, X, Discord), speed, loudness and the output folder, then **Export**.
  Without a folder the file goes next to the original (dropped files go to `~/Videos`).
- **Save** / **Save as** write a `.vproj.json` project (clips, canvas, texts, audio, overlays). **Open project** brings it back.

## 9. Tools (tab Tools)

All 45 `lk_*` tools as forms: search, fill in, **Run**. The same tools are available to the Hermes agent in chat.
Example prompts for the chat:

- "Cut the silences out of `interview.mp4` and make it 9:16 with a blurred background."
- "Burn captions from `talk.srt` into `clip.mp4` and normalise the loudness to -14 LUFS."
- "Check `final.mp4` against the Reels rules."

Reference: [Tool reference](TOOLS.md).

## 10. Keyboard

| Key | Action |
|---|---|
| Space | Play / pause |
| S | Split at the playhead |
| I / O / X | Set in / set out / remove the range |
| Delete | Delete the selected clip, text, audio or overlay |
| Left / Right | One frame back / forward (with Shift: one second) |
| Up / Down | Previous / next cut point |
| Home / End | Start / end |
| + / - | Zoom the timeline |
| Ctrl+Z, Ctrl+Shift+Z, Ctrl+S | Undo, redo, save |

## 11. Good to know

- The preview is a fast low-resolution copy. The export uses your original quality.
- The preview does not play ducking and cannot make audio louder than the source. The export does both.
- Text looks slightly different in the preview than in the export (different font).
- Texts, overlays and audio items sit at fixed times. If you cut the main clips afterwards, move them by hand.
- The preview needs H.264 or VP8 playback in the app's browser engine. Cutting and export work without it.

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| No "Video Editor" in the sidebar | Enable it under *Capabilities > Plugins*, check the right Hermes profile, restart the app. Run `python scripts/install.py` |
| "Could not start" | `hermes plugins list` must show it enabled. Fallback: `python scripts/editor.py` |
| "Preview unavailable" | Editing and export still work |
| Export fails | Run the **Media doctor** tool: it shows whether FFmpeg and its encoders are installed |

## 13. Privacy and licence

Runs locally. The editor listens only on `127.0.0.1` and reads only media below your home folder. It makes no outbound network calls.
Licence: [PolyForm Noncommercial 1.0.0](../../LICENSE): free for personal, educational, research and other non-commercial use. Commercial use needs a separate licence: contact [Lokyy.de](https://lokyy.de).

## 14. Coming soon: AI generation with Kie.ai

A separate, optional plugin is planned that lets you generate video scenes, images and sound by prompt through [Kie.ai](https://kie.ai) and place them in this editor as layers. It is **not available yet**, and this editor never contacts Kie.ai on its own. You would need your own Kie.ai account and API key, and Kie.ai bills the generation. Any referral link in that plugin will be clearly labelled and optional.

Powered by [Lokyy.de](https://lokyy.de), German Hermes Engineering.
