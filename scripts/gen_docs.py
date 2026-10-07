#!/usr/bin/env python3
"""Generate docs/en/TOOLS.md and docs/de/TOOLS.md from the tool schemas (single source of truth)."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DE = {
'lk_loudness_report':'Misst, wie laut eine Datei ist (LUFS, Spitzenpegel, Lautheitsbereich) und sagt, ob sie zu Social-Media-Zielen passt. Schreibt keine Datei.',
'lk_mute_video':'Entfernt den Ton aus einem Video; das Bild wird ohne Neu-Kodierung kopiert (sofort, verlustfrei).',
'lk_crossfade_join':'Fügt Clips mit weichem Übergang zusammen (Überblendung, Wischen, Schieben, Kreis, Pixel); Bild und Ton werden überblendet.','lk_media_doctor': 'Prüft, ob FFmpeg/ffprobe installiert sind und welche Encoder/Filter vorhanden sind (libx264, aac, drawtext, loudnorm …).',
      'lk_media_probe': 'Liest Länge, Auflösung, FPS, Codecs, Audiospuren und Dateigröße einer Datei aus.',
      'lk_detect_silence': 'Findet stille Abschnitte (Start/Ende/Dauer) ohne die Datei zu ändern.',
      'lk_detect_scenes': 'Findet Szenenwechsel und gibt die Zeitpunkte zurück.',
      'lk_extract_frame': 'Speichert ein einzelnes Standbild (PNG/JPG) zu einem Zeitpunkt.',
      'lk_trim': 'Schneidet einen Bereich heraus (Start/Ende oder Start/Dauer), schnell ohne Neu-Kodierung oder frame-genau.',
      'lk_split': 'Teilt ein Video an einem oder mehreren Zeitpunkten in mehrere Dateien.',
      'lk_join': 'Hängt mehrere Videos hintereinander (auch mit unterschiedlicher Größe/FPS).',
      'lk_remove_silence': 'Schneidet Stille automatisch heraus und fügt den Rest zusammen.',
      'lk_remove_segments': 'Entfernt angegebene Zeitbereiche und fügt den Rest nahtlos zusammen.',
      'lk_change_speed': 'Macht das Video schneller oder langsamer (Bild und Ton bleiben synchron).',
      'lk_reverse': 'Spielt kurze Clips rückwärts ab.',
      'lk_loop': 'Wiederholt einen Clip: entweder Anzahl der Durchläufe oder Ziel-Länge.',
      'lk_crop': 'Schneidet einen Bildausschnitt (x, y, Breite, Höhe) aus.',
      'lk_crop_to_aspect': 'Schneidet auf ein Seitenverhältnis zu (z. B. 9:16, 1:1, 4:5), mit wählbarem Bildanker.',
      'lk_resize': 'Ändert die Auflösung (Breite/Höhe) und behält das Seitenverhältnis.',
      'lk_rotate_flip': 'Dreht um 90/180/270 Grad oder spiegelt horizontal/vertikal.',
      'lk_pad_blur_background': 'Packt ein Video in ein anderes Format und füllt die Ränder mit unscharfem Hintergrund (z. B. 16:9 → 9:16).',
      'lk_color_adjust': 'Helligkeit, Kontrast, Sättigung und Gamma anpassen.',
      'lk_denoise_video': 'Reduziert Bildrauschen.',
      'lk_fade_video': 'Blendet das Bild ein und/oder aus (Schwarz).',
      'lk_stabilize': 'Beruhigt verwackelte Aufnahmen.',
      'lk_add_text': 'Schreibt Text ins Bild (Position, Größe, Farbe, Umriss, Box, Zeitfenster).',
      'lk_burn_captions': 'Brennt Untertitel aus einer SRT-, VTT- oder ASS-Datei fest ins Bild.',
      'lk_add_image_overlay': 'Legt ein Bild (Logo, Wasserzeichen) auf das Video.',
      'lk_picture_in_picture': 'Legt ein zweites Video klein über das Hauptvideo (Bild-in-Bild).',
      'lk_stack_videos': 'Stellt zwei Videos nebeneinander oder untereinander.',
      'lk_blur_region': 'Verpixelt oder verwischt ein festes Rechteck (Gesichter, Kennzeichen, Passwörter), für den ganzen Clip oder ein Zeitfenster. Folgt keinem bewegten Objekt.',
      'lk_extract_audio': 'Speichert die Tonspur als Audiodatei (mp3, wav, m4a …).',
      'lk_replace_audio': 'Ersetzt die Tonspur durch eine andere Audiodatei.',
      'lk_mix_music': 'Mischt Musik unter das Video, optional mit Ducking (Musik wird leiser, wenn gesprochen wird).',
      'lk_normalize_loudness': 'Gleicht die Lautheit nach EBU R128 an (z. B. -14 LUFS für Social Media).',
      'lk_sync_audio_offset': 'Verschiebt den Ton gegenüber dem Bild, um Lippen-Asynchronität zu beheben.',
      'lk_adjust_volume': 'Macht lauter oder leiser (in dB).',
      'lk_fade_audio': 'Blendet den Ton ein und/oder aus.',
      'lk_denoise_audio': 'Reduziert Rauschen in der Tonspur.',
      'lk_export_preset': 'Exportiert mit Voreinstellung für Reels, TikTok, Shorts, YouTube, X oder Discord.',
      'lk_platform_check': 'Prüft eine fertige Datei gegen die Regeln einer Plattform und nennt konkrete Korrekturen. Immer zuletzt ausführen.',
      'lk_compress_to_size': 'Komprimiert auf eine Zielgröße in MB (z. B. 25 MB für Discord).',
      'lk_to_gif': 'Erzeugt ein GIF mit guter Farbpalette.',
      'lk_contact_sheet': 'Erzeugt ein Übersichtsbild aus vielen Standbildern.',
      'lk_transcribe_captions': 'Erzeugt Untertitel (SRT) lokal mit faster-whisper. Optional: braucht ein bereits lokal vorhandenes Modell.'}

DE_GROUPS = [("A. Prüfen", 6), ("B. Schneiden & Zeit", 9), ("C. Bild", 9), ("D. Overlays & Text", 6), ("E. Ton", 9), ("F. Export & Prüfung", 6)]

GROUPS = [("A. Inspect", 6), ("B. Cut & time", 9), ("C. Picture", 9),
          ("D. Overlays & text", 6), ("E. Audio", 9), ("F. Export & check", 6)]


def load():
    spec = importlib.util.spec_from_file_location("hermes_video_editor", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_video_editor"] = mod
    spec.loader.exec_module(mod)
    from hermes_video_editor.schemas import TOOLS
    return TOOLS


def typ(p):
    t = p.get("type", "")
    t = "/".join(t) if isinstance(t, list) else t
    return "%s (%s)" % (t, "|".join(map(str, p["enum"]))) if "enum" in p else t


def render(tools):
    out = ["# Tool reference (%d tools)" % len(tools), "",
           "Generated by `scripts/gen_docs.py` from the tool schemas. Do not edit by hand.", "",
           "Every tool returns a JSON string: `{\"ok\": true, \"output\": ..., \"duration_s\": ..., \"info\": {...}}` "
           "or `{\"ok\": false, \"error\": ..., \"hint\": ..., \"ffmpeg_stderr_tail\": ...}`. "
           "`duration_s` is the length of the OUTPUT media in seconds; processing time is `info.elapsed_s`.", ""]
    it = iter(tools)
    for title, count in GROUPS:
        out += ["## " + title, ""]
        for _ in range(count):
            t = next(it)
            s = t["schema"]
            params = s["parameters"]["properties"]
            req = set(s["parameters"].get("required", []))
            out += ["### `%s`" % t["name"], "", s["description"], "", "| Parameter | Type | Required | Description |",
                    "|---|---|---|---|"]
            for k, p in params.items():
                d = p.get("description", "").replace("|", "\\|").replace("\n", " ")
                if "default" in p:
                    d += " Default: `%s`." % p["default"]
                out.append("| `%s` | %s | %s | %s |" % (k, typ(p), "yes" if k in req else "", d))
            out.append("")
    return "\n".join(out)


def render_de(tools):
    out = ["# Werkzeug-Referenz (%d Werkzeuge)" % len(tools), "",
           "Erzeugt von `scripts/gen_docs.py`. Nicht von Hand ändern. Die vollständigen Parameterbeschreibungen stehen in der "
           "[englischen Referenz](../en/TOOLS.md); hier die Kurzfassung auf Deutsch.", "",
           "Jedes Werkzeug gibt einen JSON-Text zurück: `{\"ok\": true, \"output\": ..., \"duration_s\": ...}` oder "
           "`{\"ok\": false, \"error\": ..., \"hint\": ...}`. Originaldateien werden nie verändert, es entsteht immer eine neue Datei.", ""]
    it = iter(tools)
    for title, count in DE_GROUPS:
        out += ["## " + title, "", "| Werkzeug | Was es macht | Parameter (* = Pflicht) |", "|---|---|---|"]
        for _ in range(count):
            t = next(it)
            props = t["schema"]["parameters"]["properties"]
            req = set(t["schema"]["parameters"].get("required", []))
            names = ", ".join("`%s`%s" % (k, "*" if k in req else "") for k in props)
            out.append("| `%s` | %s | %s |" % (t["name"], DE[t["name"]], names))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    tools = load()
    targets = [(ROOT / "docs" / "en" / "TOOLS.md", render(tools)), (ROOT / "docs" / "de" / "TOOLS.md", render_de(tools))]
    if "--check" in sys.argv:
        sys.exit(0 if all(t.read_text(encoding="utf-8") == txt for t, txt in targets) else 1)
    for t, txt in targets:
        t.write_text(txt, encoding="utf-8")
        print("wrote", t)
