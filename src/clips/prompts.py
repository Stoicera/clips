"""Prompts for the two model passes. German output; rules from video-to-clips.md §4 and §10."""

from __future__ import annotations

import json

SELECT_SYSTEM = """Du wählst aus dem Transkript einer langen Aufnahme Kandidaten für Kurzvideos.
Du antwortest nur mit JSON, ohne Erklärung davor oder danach."""

SELECT_USER = """Unten steht ein deutsches Transkript als nummerierte Sätze mit Start und Ende in Sekunden.
Wähle {min_clips} bis {max_clips} Clips. Jeder Clip ist ein zusammenhängender Satzbereich.

Kriterien, alle müssen gelten:
- Genau eine These je Clip.
- Der Clip enthält entweder eine Zahl mit ihrem Messdatum oder einen konkreten Befund.
- Er beginnt mit dem Satz, der die These trägt, ohne Anlauf („also", „ähm", „was ich sagen wollte").
- Er endet an einem Satzende.
- Er steht ohne Kontext, den der Zuschauer nicht hat.
- Länge {min_s:.0f} bis {max_s:.0f} Sekunden (aus den Zeiten berechnen), keine Überschneidungen.
- Lieber einen Kandidaten weglassen als ihn strecken. Eine Zahl ohne Datum in der Quelle wird nicht ergänzt; den Kandidaten dann nicht nehmen und unter "dropped" mit Grund nennen.

Antwort als JSON-Objekt:
{{"clips": [{{"start_sentence": <int>, "end_sentence": <int>, "title": "<höchstens 48 Zeichen, nüchtern>", "hook": "<erster gesprochener Satz>", "thesis": "<die eine These>", "why": "<ein Satz, warum der Clip allein steht>"}}],
 "dropped": [{{"start_sentence": <int>, "end_sentence": <int>, "reason": "<Grund>"}}]}}
Reihenfolge in "clips": der stärkste Kandidat zuerst.

Sätze:
{sentences}
"""

TEXTS_SYSTEM = """Du schreibst Begleittexte für Kurzvideos der Stoicera Software Group (Österreich).
Sprache: Deutsch (Österreich), Sie-Form, ruhig, klar, ein Gedanke je Text.
Nie: Superlative, Buzzwords, religiöses oder kriegerisches Vokabular, Hustle-Rhetorik, Emojis,
Rufzeichen, Aufforderungen über einen schlichten Satz hinaus. Jede Zahl trägt ihr Messdatum,
so wie es im Transkript steht; keine Zahl erfinden. Du antwortest nur mit JSON."""

TEXTS_USER = """Für jeden Clip unten schreibe drei Texte. Grundlage ist ausschließlich der Clip-Text.

- linkedin: 600 bis 1.300 Zeichen. Erste Zeile ist die Zahl oder der Befund. Kein Link im Text
  (der Link kommt in den ersten Kommentar). Höchstens drei Hashtags am Ende. Absätze mit Leerzeile.
- instagram: 150 bis 600 Zeichen, erste Zeile trägt den Befund, höchstens fünf Hashtags am Ende.
- youtube_title: höchstens 70 Zeichen, nüchtern, ohne Clickbait; „#Shorts" nicht nötig.
- youtube_description: ein bis drei Sätze, höchstens 400 Zeichen.

Antwort als JSON: {{"clips": [{{"index": <int>, "linkedin": "...", "instagram": "...", "youtube_title": "...", "youtube_description": "..."}}]}}

Clips:
{clips}
"""


def select_prompt(
    sentences: list[dict], min_clips: int, max_clips: int, min_s: float, max_s: float
) -> str:
    lines = [f"[{s['id']}] {s['start']:.2f}–{s['end']:.2f} {s['text']}" for s in sentences]
    return SELECT_USER.format(
        min_clips=min_clips,
        max_clips=max_clips,
        min_s=min_s,
        max_s=max_s,
        sentences="\n".join(lines),
    )


def texts_prompt(clips: list[dict]) -> str:
    slim = [
        {
            "index": c["index"],
            "title": c["title"],
            "thesis": c["thesis"],
            "duration_s": c["duration"],
            "text": c["text"],
        }
        for c in clips
    ]
    return TEXTS_USER.format(clips=json.dumps(slim, ensure_ascii=False, indent=1))
