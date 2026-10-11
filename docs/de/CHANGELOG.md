# Was ist neu

Jede Version listet, was neu ist. Der älteste Eintrag (0.3.1) beschreibt alles, was der Editor damals konnte; neuere Einträge nennen nur die Änderungen.

## 0.5.0 (2026-10-11)

Hermes und der Editor arbeiten zusammen, Sticker und GIFs und ein Layout mit Medienbibliothek.

### Hermes
- **Von Hermes erstellte Videos öffnen sich im Editor.** Das neue Werkzeug `lk_open_in_editor` übergibt ein fertiges Video (oder ein gespeichertes Projekt); die Seite Video Editor holt es ab, zeigt es und lädt es. Arbeitest du schon, bekommst du einen Hinweis mit Knopf statt einer Überraschung.
- **Eigene Einstellungsseite** unter *Settings → Plugins → Video Editor* in Hermes Desktop (neuere Versionen): Verhalten beim Öffnen, Was ist neu, Magnet, Standard-Leinwand und Hintergrund, Sprache und Modell der Untertitel. Die Option für den Agenten erscheint als Formular aus dem Einstellungsschema des Plugins.
- 46 Werkzeuge (neu: `lk_open_in_editor`).

### Ebenen
- **Bilder und GIFs** (PNG, JPG, WebP, BMP, GIF) als Sticker in der Overlay-Spur: platzieren, skalieren, ein-/ausblenden, kürzen, teilen. Ein GIF wiederholt sich beliebig lange. Transparenz bleibt erhalten.

### Layout
- Eine **Medienbibliothek** links: jede hinzugefügte Datei ist eine Karte; ein Klick legt ein Video auf die Zeitleiste, einen Ton oder Sticker an den Abspielkopf. Schnelltasten für Text, Formen, Hintergrund-Streifen und Untertitel. Die Einstellungen und Tabs sind nach rechts gewandert (Eigenschaften), die Zeitleiste bleibt unten. Die Bibliothek blendest du mit *Media* in der oberen Leiste aus.

## 0.4.0 (2026-10-09)

Mehr von dem, was ein moderner Editor bietet: eine Werkzeugleiste, Hintergründe, die sich über die Zeit ändern, Tempo, Übergänge und Look pro Clip, Ein-/Ausblenden und automatische Untertitel.

### Zeitleiste
- **Werkzeugleiste** über der Zeitleiste: Rückgängig, Wiederholen, Teilen, **Anfang / Ende auf den Abspielkopf kürzen** (Q / W), **Klonen** (Strg+D), Löschen. Sie wirkt auf einen Clip oder auf jedes ausgewählte Element einer Ebene.
- **Magnet**: gezogene Elemente rasten am Abspielkopf, am Anfang und an den Rändern anderer Elemente ein; eine dünne Linie zeigt wo. Mit einem Klick abschaltbar.
- Eine neue Spur **BG strip**: jeder Zeitbereich bekommt seinen eigenen Hintergrund (unscharfes Bild, Schwarz, Farbe, Verlauf, Bild). Streifen dürfen sich auf getrennten Spuren überlappen.

### Clips (neuer Tab Clip)
- **Tempo** von 0,25x bis 4x, der Ton folgt, und ein **Standbild** am Abspielkopf.
- **Übergänge** zwischen Clips: Überblenden, Abblenden auf Schwarz oder Weiß, Dissolve, Wischer, Schieber, Kreis, Pixel. Die Vorschau zeigt einen harten Schnitt; der Export blendet.
- **Look und Ton** pro Clip: Helligkeit, Kontrast, Sättigung, Lautstärke, Stumm, Ein- und Ausblenden.

### Ebenen
- **Ein- und Ausblenden** für Texte, Formen und Videos obendrauf.
- **Automatische Untertitel**: das Gesprochene deiner Clips wird zu bearbeitbaren Texten in einer Szene (optionales lokales `faster-whisper`, nichts wird heruntergeladen oder hochgeladen).

### Korrekturen
- Ein Element in einer Ebenen-Spur zu ziehen schiebt den Abspielkopf nicht mehr mit der Maus mit.
- Projektdateien und der Export behalten alles Obige.

## 0.3.1 (2026-10-09)

Das ist das erste Release mit vollem Funktionsumfang. Das kannst du heute tun:

### Schneiden
- Videos hineinziehen, teilen, löschen, umsortieren, kürzen; mehrere Clips laufen hintereinander. Einen markierten Bereich oder alle Stille mit einem Klick entfernen. Rückgängig und Wiederholen mit 100 Schritten.
- Wellenform, Vorschaubilder und eine schnelle Vorschau in niedriger Auflösung. Deine Originaldateien werden nie verändert.

### Bild
- Leinwand 16:9, 9:16, 1:1, 4:5 oder automatisch, in der gewünschten Auflösung.
- Jeden Clip frei verschieben und skalieren, mit Fit / Fill / Center / Reset. Ein 16:9-Clip passt in eine 9:16-Leinwand.
- Hintergrund: unscharfes Bild, Schwarz, eine Farbe, ein Verlauf oder ein eigenes Bild.

### Ebenen
- **Text** mit Größe, Farbe, Umriss, Box und Vorlagen (Title, Lower third, Caption).
- **Formen**: Rechteck, abgerundete Box, Ellipse (Farbe, Deckkraft, Größe), mit Vorlagen (Caption bar, Card, Circle, Full colour).
- **Video-Overlays** (Bild-in-Bild) mit Position, Größe, Deckkraft und optionalem Ton.
- **Audio**: Musik- und Sprachdateien mit Lautstärke, Ein-/Ausblenden, Startzeit und Ducking.
- **Szenen** bündeln Texte, Formen, Overlays und Töne, damit sie zusammen wandern.
- Beliebig viele **Spuren** pro Art; Elemente landen auf der ersten freien Spur und lassen sich zwischen Spuren ziehen. Ein Klick in der Vorschau wählt aus, was unter der Maus liegt, und zieht es.

### Export und Projekte
- Voreinstellungen für Reels, TikTok, Shorts, YouTube, X und Discord, Tempo, Lautheit (EBU R128) und eine Plattform-Prüfung.
- Ordnerauswahl mit „Neuer Ordner“. Projekte (`.vproj.json`) behalten Clips, Leinwand, Hintergrund, Texte, Formen, Szenen, Spuren, Audio und Overlays.

### Für den Agenten
- 45 lokale FFmpeg-Werkzeuge (`lk_*`), darunter Lautheitsbericht, Video stummschalten und Überblend-Verbindung. Ausgabedateien bekommen nur Medien-, Bild- oder `.srt`-Endungen, und Ergebnisse entstehen in einer temporären Datei, sodass ein fehlgeschlagener Lauf nie eine vorhandene Datei beschädigt oder entfernt.

### Hilfe
- Diese Anleitung und dieses Änderungsprotokoll, auf Englisch und Deutsch, im Editor (Knopf Help).
- Später als separates optionales Plugin: KI-Video, -Bild und -Ton über Kie.ai.

### Lizenz
- PolyForm Noncommercial 1.0.0: frei für nicht-kommerzielle Nutzung; kommerzielle Nutzung braucht eine eigene Lizenz.
