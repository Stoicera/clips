# Beleg: erster Lauf, 15.10.2026

Quelle: synthetische Testaufnahme (`scripts/testaufnahme.py`): das Teleprompter-Skript V01 der
K7-Longform-Reihe, gelesen von der macOS-Stimme „Anna“, über einer 1920×1080-Fläche mit zwei
Platzhalterflächen statt Sprecher und Bildschirm. Grund: die drei veröffentlichten Filme sind
24, 32 und 60 Sekunden lang, zu kurz für fünf Clips; eine echte lange Aufnahme gibt es erst ab
23.10.2026. Kein Gesicht, keine echte Stimme, nichts hat den Rechner verlassen außer dem
Transkripttext (an OpenRouter → Claude Opus 5.5).

| Schritt | Messung (Mac M1, 8 GB) |
|---|---|
| Transkription whisper.cpp large-v3-turbo, 681 s Audio | 103 s, 1.483 Wörter, 178 Sätze |
| Auswahl (ein Modellaufruf) | 48 s, 7 Kandidaten angenommen, 0 vom Validator verworfen, 7 vom Modell mit Grund verworfen |
| Schnitt 7 Clips (Crop, Titelkarte, Untertitel, Loudnorm) | 104 s |
| Texte (ein Modellaufruf) | ~60 s |

Dateien hier: `report.md` (ffprobe-Fakten, Lautheit, Verworfenes), `clips.json`, `captions.md`,
`01_untertitel.ass`, Einzelbilder aus Clip 01 (Sekunde 0: Titelkarte; Sekunde 20: Untertitel in
der Safe Area) und Clip 07. Die MP4s liegen nicht im Repo.

Bekannte Schwäche dieses Laufs: Satz 0 enthält eine Regieanweisung aus dem Skript („Gesicht groß,
zweimal aufnehmen“), die das Hilfsskript nicht entfernt hatte; das Modell hat den Satz korrekt
verworfen. Das Hilfsskript ist inzwischen korrigiert.
