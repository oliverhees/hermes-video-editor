# Werkzeug-Referenz (42 Werkzeuge)

Erzeugt von `scripts/gen_docs.py`. Nicht von Hand ändern. Die vollständigen Parameterbeschreibungen stehen in der [englischen Referenz](../en/TOOLS.md); hier die Kurzfassung auf Deutsch.

Jedes Werkzeug gibt einen JSON-Text zurück: `{"ok": true, "output": ..., "duration_s": ...}` oder `{"ok": false, "error": ..., "hint": ...}`. Originaldateien werden nie verändert, es entsteht immer eine neue Datei.

## A. Prüfen

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_media_doctor` | Prüft, ob FFmpeg/ffprobe installiert sind und welche Encoder/Filter vorhanden sind (libx264, aac, drawtext, loudnorm …). | `timeout_s` |
| `lk_media_probe` | Liest Länge, Auflösung, FPS, Codecs, Audiospuren und Dateigröße einer Datei aus. | `input`*, `timeout_s` |
| `lk_detect_silence` | Findet stille Abschnitte (Start/Ende/Dauer) ohne die Datei zu ändern. | `input`*, `timeout_s`, `noise_db`, `min_duration_s` |
| `lk_detect_scenes` | Findet Szenenwechsel und gibt die Zeitpunkte zurück. | `input`*, `timeout_s`, `threshold` |
| `lk_extract_frame` | Speichert ein einzelnes Standbild (PNG/JPG) zu einem Zeitpunkt. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `time`, `format` |

## B. Schneiden & Zeit

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_trim` | Schneidet einen Bereich heraus (Start/Ende oder Start/Dauer), schnell ohne Neu-Kodierung oder frame-genau. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `start`, `end`, `duration`, `mode`, `crf` |
| `lk_split` | Teilt ein Video an einem oder mehreren Zeitpunkten in mehrere Dateien. | `input`*, `output_dir`, `overwrite`, `timeout_s`, `times`*, `mode`, `crf` |
| `lk_join` | Hängt mehrere Videos hintereinander (auch mit unterschiedlicher Größe/FPS). | `output`, `output_dir`, `overwrite`, `timeout_s`, `inputs`*, `mode`, `crf` |
| `lk_remove_silence` | Schneidet Stille automatisch heraus und fügt den Rest zusammen. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `noise_db`, `min_silence_s`, `padding_s`, `crf` |
| `lk_remove_segments` | Entfernt angegebene Zeitbereiche und fügt den Rest nahtlos zusammen. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `segments`*, `crf` |
| `lk_change_speed` | Macht das Video schneller oder langsamer (Bild und Ton bleiben synchron). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `factor`*, `crf` |
| `lk_reverse` | Spielt kurze Clips rückwärts ab. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `crf` |
| `lk_loop` | Wiederholt einen Clip: entweder Anzahl der Durchläufe oder Ziel-Länge. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `count`, `target_duration_s`, `crf` |

## C. Bild

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_crop` | Schneidet einen Bildausschnitt (x, y, Breite, Höhe) aus. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `width`*, `height`*, `x`, `y`, `crf` |
| `lk_crop_to_aspect` | Schneidet auf ein Seitenverhältnis zu (z. B. 9:16, 1:1, 4:5), mit wählbarem Bildanker. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `aspect`*, `anchor`, `output_width`, `crf` |
| `lk_resize` | Ändert die Auflösung (Breite/Höhe) und behält das Seitenverhältnis. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `preset`, `width`, `height`, `keep_aspect`, `crf` |
| `lk_rotate_flip` | Dreht um 90/180/270 Grad oder spiegelt horizontal/vertikal. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `rotate`, `hflip`, `vflip`, `crf` |
| `lk_pad_blur_background` | Packt ein Video in ein anderes Format und füllt die Ränder mit unscharfem Hintergrund (z. B. 16:9 → 9:16). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `width`, `height`, `blur_strength`, `crf` |
| `lk_color_adjust` | Helligkeit, Kontrast, Sättigung und Gamma anpassen. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `brightness`, `contrast`, `saturation`, `gamma`, `crf` |
| `lk_denoise_video` | Reduziert Bildrauschen. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `strength`, `crf` |
| `lk_fade_video` | Blendet das Bild ein und/oder aus (Schwarz). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `fade_in_s`, `fade_out_s`, `audio`, `crf` |
| `lk_stabilize` | Beruhigt verwackelte Aufnahmen. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `strength`, `edge`, `crf` |

## D. Overlays & Text

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_add_text` | Schreibt Text ins Bild (Position, Größe, Farbe, Umriss, Box, Zeitfenster). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `text`*, `position`, `font_size`, `color`, `outline_px`, `box`, `box_color`, `box_opacity`, `margin_px`, `font_file`, `start`, `end`, `crf` |
| `lk_burn_captions` | Brennt Untertitel aus einer SRT-, VTT- oder ASS-Datei fest ins Bild. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `captions`*, `font_size`, `outline_px`, `bottom_margin_px`, `reels_safe`, `color`, `bold`, `font_name`, `crf` |
| `lk_add_image_overlay` | Legt ein Bild (Logo, Wasserzeichen) auf das Video. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `image`*, `corner`, `scale_percent`, `opacity`, `margin_px`, `start`, `end`, `crf` |
| `lk_picture_in_picture` | Legt ein zweites Video klein über das Hauptvideo (Bild-in-Bild). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `pip_input`*, `corner`, `scale_percent`, `margin_px`, `audio`, `loop_pip`, `start`, `end`, `crf` |
| `lk_stack_videos` | Stellt zwei Videos nebeneinander oder untereinander. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `input2`*, `layout`, `audio`, `crf` |
| `lk_blur_region` | Verpixelt oder verwischt ein festes Rechteck (Gesichter, Kennzeichen, Passwörter), für den ganzen Clip oder ein Zeitfenster. Folgt keinem bewegten Objekt. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `x`*, `y`*, `width`*, `height`*, `mode`, `strength`, `start`, `end`, `crf` |

## E. Ton

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_extract_audio` | Speichert die Tonspur als Audiodatei (mp3, wav, m4a …). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `format`, `bitrate_kbps`, `audio_track` |
| `lk_replace_audio` | Ersetzt die Tonspur durch eine andere Audiodatei. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `audio`*, `mode` |
| `lk_mix_music` | Mischt Musik unter das Video, optional mit Ducking (Musik wird leiser, wenn gesprochen wird). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `music`*, `music_volume_db`, `ducking`, `duck_strength`, `fade_out_s` |
| `lk_normalize_loudness` | Gleicht die Lautheit nach EBU R128 an (z. B. -14 LUFS für Social Media). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `target_lufs`, `true_peak_db`, `lra`, `verify` |
| `lk_sync_audio_offset` | Verschiebt den Ton gegenüber dem Bild, um Lippen-Asynchronität zu beheben. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `offset_ms`* |
| `lk_adjust_volume` | Macht lauter oder leiser (in dB). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `db`, `factor`, `prevent_clipping` |
| `lk_fade_audio` | Blendet den Ton ein und/oder aus. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `fade_in_s`, `fade_out_s` |
| `lk_denoise_audio` | Reduziert Rauschen in der Tonspur. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `preset` |

## F. Export & Prüfung

| Werkzeug | Was es macht | Parameter (* = Pflicht) |
|---|---|---|
| `lk_export_preset` | Exportiert mit Voreinstellung für Reels, TikTok, Shorts, YouTube, X oder Discord. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `preset`*, `fit`, `crf` |
| `lk_platform_check` | Prüft eine fertige Datei gegen die Regeln einer Plattform und nennt konkrete Korrekturen. Immer zuletzt ausführen. | `input`*, `timeout_s`, `platform`*, `check_loudness` |
| `lk_compress_to_size` | Komprimiert auf eine Zielgröße in MB (z. B. 25 MB für Discord). | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `target_mb`*, `audio_kbps`, `allow_downscale` |
| `lk_to_gif` | Erzeugt ein GIF mit guter Farbpalette. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `start`, `end`, `duration`, `fps`, `width`, `max_colors`, `loop`, `dither` |
| `lk_contact_sheet` | Erzeugt ein Übersichtsbild aus vielen Standbildern. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `columns`, `rows`, `thumb_width`, `format` |
| `lk_transcribe_captions` | Erzeugt Untertitel (SRT) lokal mit faster-whisper. Optional: braucht ein bereits lokal vorhandenes Modell. | `input`*, `output`, `output_dir`, `overwrite`, `timeout_s`, `model`, `model_path`, `language` |
