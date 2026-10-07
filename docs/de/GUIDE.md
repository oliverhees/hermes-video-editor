# Video Editor: Anleitung

Alles läuft auf deinem Rechner mit FFmpeg. Kein Konto, keine Cloud, kein API-Key.

## 1. Los geht's in 3 Schritten

1. **Video Editor** in der Hermes-Desktop-Seitenleiste öffnen (oder `python scripts/editor.py` für den Browser).
2. **Videos ins Fenster ziehen** oder auf **Add clip...** klicken.
3. Schneiden, platzieren, Text und Musik hinzufügen, dann den Tab **Export** öffnen.

Der Editor verändert nie deine Originaldateien. Jeder Export erzeugt eine neue Datei.

## 2. Das Fenster

| Bereich | Was es ist |
|---|---|
| Links | Tabs: **Edit, Picture, Text, Overlay, Sound, Tools, Export** |
| Mitte | Vorschau deiner Leinwand. Bild, Text oder Overlay direkt hier ziehen |
| Unten | Zeitleiste: Clips, Wellenform, Spur **Text**, Spur **Audio**, Spur **Overlay** |

## 3. Schneiden (Tab Edit)

| Das willst du | So geht's |
|---|---|
| Clip teilen | Abspielkopf an die Schnittstelle, **S** drücken |
| Clip löschen (Lücke schließt sich) | Clip auswählen, **Entf** drücken |
| Bereich entfernen | **I** setzt den Anfang, **O** das Ende, **X** entfernt und schließt die Lücke. Oder Shift halten und auf der Zeitleiste ziehen |
| Reihenfolge ändern | Clip nach links oder rechts ziehen |
| Clip kürzen | Linken oder rechten Rand ziehen |
| Alle Stille entfernen | Pegel und kürzeste Stille einstellen, **Remove silences** klicken (für den gewählten Clip oder alle) |
| Rückgängig / Wiederholen | **Strg+Z** / **Strg+Umschalt+Z** |

## 4. Bild (Tab Picture)

- **Leinwand**: 16:9, 9:16, 1:1, 4:5 oder automatisch, plus Auflösung. Die Ausgabe hat genau diese Größe.
- **Hintergrund** hinter Bildern, die die Leinwand nicht füllen: unscharfe Kopie, Schwarz oder eine Farbe.
- **Position und Größe jedes Clips**: Clip auswählen, dann in der Vorschau ziehen, mit dem Mausrad zoomen, oder die Regler und **Fit / Fill / Center / Reset** nutzen.
  Teile einen Clip zuerst, um jeden Teil anders zu platzieren (z. B. wenn sich die Person bewegt).
  **Fill** lässt einen 16:9-Clip eine 9:16-Leinwand ausfüllen.

## 5. Video obendrauf (Tab Overlay)

Eine zweite Videospur über dem Hauptbild: Reaktions-Clip, Logo-Animation, B-Roll.

1. Abspielkopf setzen, Tab **Overlay** öffnen, **Add a video on top...** klicken.
2. In der Vorschau ziehen, um es zu platzieren. Mausrad oder Regler **Size** skaliert.
   Die Ecken-Knöpfe setzen es in eine Ecke, **Full picture** füllt die Leinwand.
3. In der Spur **Overlay**: ziehen verschiebt es in der Zeit, an den Rändern ziehen kürzt es.
4. **Opacity** blendet es durch. **Play its sound** mischt den eigenen Ton des Overlays dazu (standardmäßig aus).

## 6. Text (Tab Text)

1. Abspielkopf setzen, **Add text at the playhead** klicken und tippen.
2. Größe, Farbe, Umriss und Box. Vorlagen: **Title, Lower third, Caption**.
3. Text in der Vorschau ziehen. In der Spur **Text** verschieben, an den Rändern ändern, wie lange er sichtbar ist.

## 7. Ton (Tab Sound)

- **Audiospur** (Musik, Sprecher): **Add audio...** nimmt jede Audiodatei (oder ein Video mit Ton).
  Lautstärke (dB), Ein-/Ausblenden und Startzeit einstellen. **Ducking** macht die Musik leiser, solange das Video spricht.
- **Lautheit**: nach EBU R128 angleichen (-14 LUFS passt für Reels, TikTok, Shorts und YouTube).
- Eine Sprachaufnahme direkt im Editor ist nicht möglich (der App-Rahmen hat kein Mikrofon). Nimm eine Datei auf und füge sie hinzu.

## 8. Export und Projekte (Tab Export)

- **Voreinstellung** (Reels, TikTok, Shorts, YouTube, X, Discord), Tempo, Lautheit und Ausgabeordner wählen, dann **Export**.
  Ohne Ordner landet die Datei neben dem Original (hineingezogene Dateien landen in `~/Videos`).
- **Save** / **Save as** speichern ein `.vproj.json`-Projekt (Clips, Leinwand, Texte, Audio, Overlays). **Open project** holt es zurück.

## 9. Alle Werkzeuge (Tab Tools)

Alle 42 `lk_*`-Werkzeuge als Formular: suchen, ausfüllen, **Run**. Dieselben Werkzeuge nutzt der Hermes-Agent im Chat.
Beispiele für den Chat:

- „Schneide die Stille aus `interview.mp4` und mach es 9:16 mit unscharfem Hintergrund.“
- „Brenne die Untertitel aus `talk.srt` in `clip.mp4` und gleiche die Lautheit auf -14 LUFS an.“
- „Prüfe `final.mp4` gegen die Reels-Regeln.“

Nachschlagewerk: [Werkzeug-Referenz](TOOLS.md).

## 10. Tastatur

| Taste | Aktion |
|---|---|
| Leertaste | Abspielen / Pause |
| S | Am Abspielkopf teilen |
| I / O / X | Anfang setzen / Ende setzen / Bereich entfernen |
| Entf | Gewählten Clip, Text, Ton oder Overlay löschen |
| Links / Rechts | Ein Bild zurück / vor (mit Umschalt: eine Sekunde) |
| Hoch / Runter | Voriger / nächster Schnittpunkt |
| Pos1 / Ende | Anfang / Ende |
| + / - | Zeitleiste zoomen |
| Strg+Z, Strg+Umschalt+Z, Strg+S | Rückgängig, Wiederholen, Speichern |

## 11. Gut zu wissen

- Die Vorschau ist eine schnelle Kopie in niedriger Auflösung. Der Export nutzt deine Original-Qualität.
- Die Vorschau spielt kein Ducking ab und kann Ton nicht lauter machen als die Quelle. Der Export kann beides.
- Text sieht in der Vorschau etwas anders aus als im Export (andere Schrift).
- Texte, Overlays und Audio-Elemente liegen auf festen Zeiten. Schneidest du danach die Hauptclips, verschiebe sie von Hand.
- Die Vorschau braucht H.264- oder VP8-Wiedergabe in der Browser-Engine der App. Schneiden und Export gehen auch ohne.

## 12. Probleme lösen

| Problem | Lösung |
|---|---|
| Kein „Video Editor“ in der Seitenleiste | Unter *Capabilities > Plugins* aktivieren, richtiges Hermes-Profil prüfen, App neu starten. `python scripts/install.py` ausführen |
| „Could not start“ | `hermes plugins list` muss es als aktiv zeigen. Ersatz: `python scripts/editor.py` |
| „Preview unavailable“ | Schneiden und Export funktionieren trotzdem |
| Export schlägt fehl | Werkzeug **Media doctor** starten: zeigt, ob FFmpeg und die Encoder installiert sind |

## 13. Datenschutz und Lizenz

Läuft lokal. Der Editor hört nur auf `127.0.0.1` und liest nur Mediendateien unterhalb deines Home-Ordners. Er macht keine ausgehenden Netzwerkaufrufe.
Lizenz: [PolyForm Noncommercial 1.0.0](../../LICENSE): frei für private, schulische, Forschungs- und andere nicht-kommerzielle Nutzung. Kommerzielle Nutzung braucht eine eigene Lizenz: Kontakt über [Lokyy.de](https://lokyy.de).

Powered by [Lokyy.de](https://lokyy.de), German Hermes Engineering.
