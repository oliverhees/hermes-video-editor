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
| Links | Tabs: **Edit, Picture, Text, Shape, Overlay, Sound, Scene, Tools, Export** |
| Mitte | Vorschau deiner Leinwand. **Klicke auf das, was du siehst** (Text, Form, Video obendrauf oder Clip), um es auszuwählen, dann ziehen |
| Unten | Zeitleiste: Clips und Wellenform, darunter Spuren für **Scene, Text, Overlay, Shape und Audio** |

**Spuren.** Jede Art kann mehrere Spuren haben. So legst du mehrere Texte, Formen, Videos oder Töne übereinander: Ein neues Element kommt auf die erste freie Spur, und das Menü **Tracks...** über der Zeitleiste fügt eine Spur hinzu oder entfernt sie. Ziehe ein Element nach oben oder unten, um die Spur zu wechseln. Eine höhere Spur liegt weiter vorn. Reihenfolge von hinten nach vorn: Video, Formen, Videos obendrauf, Texte.

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
- **Hintergrund** hinter Bildern, die die Leinwand nicht füllen (zum Beispiel wenn du das Video kleiner machst oder 9:16 nutzt): unscharfe Kopie, Schwarz, eine Farbe, ein Verlauf von oben nach unten oder **ein eigenes Bild**.
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
4. Mehrere Texte nacheinander: den nächsten an einer späteren Position des Abspielkopfs hinzufügen. Mehrere zur selben Zeit liegen auf getrennten Spuren.

### Formen

Im Tab **Shape** fügst du ein farbiges Rechteck, eine abgerundete Box oder eine Ellipse für ein Zeitfenster hinzu: ein Hintergrund unter einer Zeile (**Caption bar**), eine **Card**, einen **Circle** oder ein **Full colour**-Feld. Farbe, Deckkraft, Breite, Höhe und Rundung einstellen, in der Vorschau ziehen, mit dem Mausrad skalieren. Text auf einer höheren Spur steht vor der Form.

### Szenen

Eine Szene bündelt Texte, Formen, Videos obendrauf und Töne. Bereich mit **I** und **O** markieren (oder den Abspielkopf auf das erste Element setzen), den Tab **Scene** öffnen und **Bundle items into a scene** klicken. Ziehst du die Szene in ihrer Spur, wandert alles darin mit. **Copy scene** dupliziert sie samt Inhalt, **Ungroup** behält die Elemente, der rote Knopf löscht sie mit. Die Hauptclips gehören nicht zu einer Szene.

## 7. Ton (Tab Sound)

- **Audiospur** (Musik, Sprecher): **Add audio...** nimmt jede Audiodatei (oder ein Video mit Ton).
  Lautstärke (dB), Ein-/Ausblenden und Startzeit einstellen. **Ducking** macht die Musik leiser, solange das Video spricht.
- **Lautheit**: nach EBU R128 angleichen (-14 LUFS passt für Reels, TikTok, Shorts und YouTube).
- Eine Sprachaufnahme direkt im Editor ist nicht möglich (der App-Rahmen hat kein Mikrofon). Nimm eine Datei auf und füge sie hinzu.

## 8. Export und Projekte (Tab Export)

- **Voreinstellung** (Reels, TikTok, Shorts, YouTube, X, Discord), Tempo, Lautheit und Ausgabeordner wählen, dann **Export**.
  Klicke das Ordnerfeld (oder **Choose...**), um deine Ordner zu durchsuchen und einen neuen anzulegen. Ohne Ordner landet die Datei neben dem Original (hineingezogene Dateien landen in `~/Videos`).
- **Save** / **Save as** speichern ein `.vproj.json`-Projekt (Clips, Leinwand, Hintergrund, Texte, Formen, Szenen, Spuren, Audio, Overlays). Der Speichern-Dialog startet neben deinem Video und kann Ordner anlegen. **Open project** holt es zurück.

## 9. Alle Werkzeuge (Tab Tools)

Alle 45 `lk_*`-Werkzeuge als Formular: suchen, ausfüllen, **Run**. Dieselben Werkzeuge nutzt der Hermes-Agent im Chat.
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
| Entf | Gewählten Clip, Text, Form, Szene, Ton oder Overlay löschen |
| Links / Rechts | Ein Bild zurück / vor (mit Umschalt: eine Sekunde) |
| Hoch / Runter | Voriger / nächster Schnittpunkt |
| Pos1 / Ende | Anfang / Ende |
| + / - | Zeitleiste zoomen |
| Strg+Z, Strg+Umschalt+Z, Strg+S | Rückgängig, Wiederholen, Speichern |

## 11. Gut zu wissen

- Die Vorschau ist eine schnelle Kopie in niedriger Auflösung. Der Export nutzt deine Original-Qualität.
- Die Vorschau spielt kein Ducking ab und kann Ton nicht lauter machen als die Quelle. Der Export kann beides.
- Text sieht in der Vorschau etwas anders aus als im Export (andere Schrift).
- Texte, Formen, Overlays und Audio-Elemente liegen auf festen Zeiten. Schneidest du danach die Hauptclips, verschiebe sie von Hand (oder bündle sie in einer Szene und verschiebe diese).
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

## 14. Bald: KI-Erzeugung mit Kie.ai

Geplant ist ein separates, optionales Plugin, mit dem du über [Kie.ai](https://kie.ai) Video-Szenen, Bilder und Ton per Prompt erzeugst und als Ebenen in diesen Editor legst. Es ist **noch nicht verfügbar**, und dieser Editor nimmt von sich aus nie Kontakt zu Kie.ai auf. Du bräuchtest ein eigenes Kie.ai-Konto und einen API-Key, und Kie.ai stellt die Erzeugung in Rechnung. Ein Empfehlungslink in diesem Plugin wäre klar gekennzeichnet und freiwillig.

Powered by [Lokyy.de](https://lokyy.de), German Hermes Engineering.
