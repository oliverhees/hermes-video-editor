# Was ist neu

Jede Version listet, was neu ist. Der erste Eintrag (0.3.1) beschreibt alles, was der Editor heute kann; spätere Einträge nennen nur die Änderungen.

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
