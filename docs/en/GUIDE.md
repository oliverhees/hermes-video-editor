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
| Left | Tabs: **Edit, Picture, Text, Shape, Overlay, Sound, Scene, Tools, Export** |
| Centre | Preview of your canvas. **Click what you see** (a text, a shape, a video on top or the clip) to select it, then drag it |
| Bottom | Timeline: clips and waveform, then lanes for **Scene, Text, Overlay, Shape and Audio** |

**Tracks.** Every lane can have several tracks. Put several texts, shapes, videos or sounds on top of each other: a new item goes to the first free track, and the **Tracks...** menu above the timeline adds or removes a track. Drag an item up or down to change its track. A higher track is in front. Order from back to front: video, shapes, videos on top, texts.

## 3. Cut (tab Edit)

| Do this | How |
|---|---|
| Split a clip | Put the playhead where you want the cut, press **S** |
| Delete a clip (gap closes) | Select it, press **Delete** |
| Remove a range | **I** sets the start, **O** the end, **X** removes it and closes the gap. Or hold Shift and drag on the timeline |
| Re-order clips | Drag a clip left or right |
| Trim a clip | Drag its left or right edge |
| Remove all silences | Set the level and shortest silence, click **Remove silences** (on the selected clip, or on all) |
| Trim to the playhead | **Q** cuts away everything before the playhead, **W** everything after it (the toolbar buttons *Trim start* / *Trim end*) |
| Clone | **Ctrl+D**, or the *Clone* button: a copy right behind the original |
| Undo / redo | **Ctrl+Z** / **Ctrl+Shift+Z** |

**The toolbar above the timeline** has *Undo, Redo, Split, Trim start, Trim end, Clone, Delete* and the **Magnet**. The buttons act on whatever is selected: a clip, or one item of a layer (text, shape, video on top, sound, background strip). Nothing selected means the clip under the playhead. With the **Magnet** on, items you drag snap to the playhead, the start of the timeline and the edges of other items (a thin line shows where).

## 4. Picture (tab Picture)

- **Canvas**: 16:9, 9:16, 1:1, 4:5 or auto, plus the resolution. The output has exactly this size.
- **Background** behind pictures that do not fill the canvas (for example when you make the video smaller or use 9:16): blurred copy, black, one colour, a gradient from top to bottom, or **a picture of your own**.
- **Position and size of each clip**: select a clip, then drag it in the preview, use the mouse wheel, or the sliders and **Fit / Fill / Center / Reset**.
  Split a clip first to place each part differently (for example when the speaker moves).
  **Fill** makes a 16:9 clip cover a 9:16 canvas.

### Background strips

The **BG strip** lane lets the canvas background change over time: pick a time range, give it its own look (blurred picture, black, a colour, a gradient or a picture). Click **Add a strip at the playhead** in the Picture tab, drag it on its **BG strip** lane, drag its edges for the length, and use the Background controls to change it. With no strip selected the controls change the project background that applies everywhere else. Strips can overlap on separate tracks; the higher track is in front. A strip is only visible where the picture does not fill the canvas.

### Clip tab: speed, still frame, transitions, look and sound

Everything here applies to the selected clip (or the clip under the playhead):

- **Speed** from 0.25× to 4×. The sound follows without changing its pitch. The clip gets shorter or longer on the timeline.
- **Freeze frame here** splits the clip at the playhead and inserts the frame as a still picture for the time you set. It has no sound.
- **Transition into this clip** blends the clip before into this one (fade, dip to black or white, dissolve, wipes, slides, circle, pixelate). The two clips overlap by the length of the transition, at most half of the shorter clip. The preview shows a hard cut, the export blends.
- **Look**: brightness, contrast, saturation. **Sound**: volume, mute, fade in and fade out (the picture dips into the background). *Use for all clips* copies the look and sound to every clip. The preview approximates the look; the export is exact.

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
4. **Fade in** and **fade out** soften the start and end of a text; shapes and videos on top have the same two sliders.
5. Several texts one after another: add the next one at a later playhead position. Several at the same time land on separate tracks.

### Automatic subtitles

In the **Text** tab choose the clips, the spoken language and a model size and click **Make subtitles from speech**. The speech of your clips becomes normal texts (bottom of the picture, with a box) inside a scene called *Captions*. Correct a text by clicking it, restyle it, or move the whole scene. It uses the optional local package `faster-whisper` and a speech model that is already on your computer; nothing is downloaded and nothing leaves your computer. Cuts and speed changes are respected.

### Shapes

The **Shape** tab adds a coloured rectangle, rounded box or ellipse for a time window: a backing under a caption (**Caption bar**), a **Card**, a **Circle** or a **Full colour** field. Set colour, opacity, width, height and roundness, drag it in the preview, use the mouse wheel to resize. Text on a higher track is shown in front of the shape.

### Scenes

A scene bundles texts, shapes, videos on top and sounds. Mark a range with **I** and **O** (or put the playhead on the first item), open the **Scene** tab and click **Bundle items into a scene**. Drag the scene on its lane and everything inside moves along. **Copy scene** duplicates it with its items, **Ungroup** keeps the items, the red button deletes them too. The main clips are not part of a scene.

## 7. Sound (tab Sound)

- **Audio track** (music, voice-over): **Add audio...** takes any audio file (or a video with sound).
  Set volume (dB), fade in/out and start time. **Ducking** lowers the music while the video speaks.
- **Loudness**: normalise to EBU R128 (-14 LUFS suits Reels, TikTok, Shorts and YouTube).
- Recording a voice-over inside the editor is not possible (the app frame has no microphone). Record a file and add it.

## 8. Export and projects (tab Export)

- Choose a **preset** (Reels, TikTok, Shorts, YouTube, X, Discord), speed, loudness and the output folder, then **Export**.
  Click the folder field (or **Choose...**) to browse your folders and create a new one. Without a folder the file goes next to the original (dropped files go to `~/Videos`).
- **Save** / **Save as** write a `.vproj.json` project (clips, canvas, background, texts, shapes, scenes, tracks, audio, overlays). The save dialog starts next to your video and can create folders. **Open project** brings it back.

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
| S | Split the selected item (or the clip) at the playhead |
| Q / W | Trim the start / the end to the playhead |
| Ctrl+D | Clone the selected item or clip |
| I / O / X | Set in / set out / remove the range |
| Delete | Delete the selected clip, text, shape, scene, audio or overlay |
| Left / Right | One frame back / forward (with Shift: one second) |
| Up / Down | Previous / next cut point |
| Home / End | Start / end |
| + / - | Zoom the timeline |
| Ctrl+Z, Ctrl+Shift+Z, Ctrl+S | Undo, redo, save |

## 11. Good to know

- **What's new** (top bar) shows the changelog of this version; it opens by itself the first time after an update.
- The preview is a fast low-resolution copy. The export uses your original quality.
- The preview does not play ducking and cannot make audio louder than the source. The export does both.
- Text looks slightly different in the preview than in the export (different font).
- Speed, still frames and transitions change the length of the main track. Texts, shapes, overlays, background strips and audio items sit at fixed times and do not follow; bundle them in a scene and move that.
- Texts, shapes, overlays and audio items sit at fixed times. If you cut the main clips afterwards, move them by hand (or bundle them in a scene and move that).
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
