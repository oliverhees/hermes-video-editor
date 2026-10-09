# What's new

Every release lists what is new in it. The first entry (0.3.1) describes everything that is in the editor today; later entries only list what changed.

## 0.3.1 (2026-10-09)

This is the first release with a full feature set. What you can do today:

### Edit
- Drop videos in, split, delete, reorder, trim; several clips play back to back. Remove a marked range or all silences in one click. Undo and redo with 100 steps.
- Waveform, thumbnails and a fast low-resolution preview. Your original files are never changed.

### Picture
- Canvas 16:9, 9:16, 1:1, 4:5 or auto, in the resolution you choose.
- Move and scale every clip freely, with Fit / Fill / Center / Reset. A 16:9 clip fits into a 9:16 canvas.
- Background: blurred picture, black, one colour, a gradient or a picture of your own.

### Layers
- **Text** with size, colour, outline, box and presets (Title, Lower third, Caption).
- **Shapes**: rectangle, rounded box, ellipse (colour, opacity, size), with presets (Caption bar, Card, Circle, Full colour).
- **Video overlays** (picture-in-picture) with position, size, opacity and optional sound.
- **Audio**: music and voice-over files with volume, fades, start time and ducking.
- **Scenes** bundle texts, shapes, overlays and sounds, so they move together.
- Any number of **tracks** per kind; items go to the first free track, you can drag them between tracks. A click on the preview selects what is under the mouse and drags it.

### Export and projects
- Presets for Reels, TikTok, Shorts, YouTube, X and Discord, speed, loudness (EBU R128) and a platform check.
- A folder picker with "new folder". Projects (`.vproj.json`) keep clips, canvas, background, texts, shapes, scenes, tracks, audio and overlays.

### For the agent
- 45 local FFmpeg tools (`lk_*`), including loudness report, mute video and cross-fade join. Output files only get media, picture or `.srt` suffixes, and results are built in a temporary file, so an existing file is never damaged or removed by a failed run.

### Help
- This guide and this changelog, in English and German, inside the editor (Help button).
- Coming later as a separate optional plugin: AI video, image and sound via Kie.ai.

### Licence
- PolyForm Noncommercial 1.0.0: free for non-commercial use; commercial use needs a separate licence.
