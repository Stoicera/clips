"""Burnt-in subtitles as ASS: ≤ 2 lines × 38 characters, Inter, inside the safe area.

Canvas 1080×1920. Top 240 px and bottom 420 px stay free of text (platform overlays).
Word-by-word highlighting (Cobalt) is available behind `highlight=True`, off by default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

INK = "&H00271811"  # #111827 in ASS BGR order
WHITE = "&H00FFFFFF"
COBALT = "&H00E85825"  # #2558E8
_SENTENCE_END = re.compile(r"[.!?…]$")
_CLAUSE_END = re.compile(r"[,;:]$")


@dataclass
class Cue:
    start: float
    end: float
    lines: list[str]
    words: list[dict] = field(default_factory=list)


def _wrap(words: list[str], max_chars: int) -> list[str]:
    lines, line = [], ""
    for w in words:
        candidate = f"{line} {w}".strip()
        if len(candidate) > max_chars and line:
            lines.append(line)
            line = w
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def _fits(words: list[str], max_chars: int, max_lines: int) -> bool:
    return len(_wrap(words, max_chars)) <= max_lines and all(len(w) <= max_chars for w in words)


def build_cues(
    words: list[dict],
    max_chars: int = 38,
    max_lines: int = 2,
    max_duration: float = 4.0,
    max_gap: float = 1.0,
    offset: float = 0.0,
) -> list[Cue]:
    """Groups words into cues; breaks at sentence ends, pauses, duration or width."""
    cues: list[Cue] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            texts = [w["text"] for w in current]
            cues.append(
                Cue(
                    start=round(current[0]["start"] - offset, 3),
                    end=round(current[-1]["end"] - offset, 3),
                    lines=_wrap(texts, max_chars),
                    words=list(current),
                )
            )
            current.clear()

    for w in words:
        if current:
            gap = w["start"] - current[-1]["end"]
            too_long = w["end"] - current[0]["start"] > max_duration
            if (
                gap > max_gap
                or too_long
                or not _fits([x["text"] for x in current] + [w["text"]], max_chars, max_lines)
            ):
                flush()
        current.append(w)
        if _SENTENCE_END.search(w["text"]):
            flush()
        elif (
            _CLAUSE_END.search(w["text"])
            and len(_wrap([x["text"] for x in current], max_chars)) >= max_lines
        ):
            flush()
    flush()
    return cues


def format_ass_time(seconds: float) -> str:
    cs = int(round(max(seconds, 0.0) * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _highlighted(cue: Cue, max_chars: int) -> list[str]:
    """One Dialogue line per word, the spoken word in Cobalt. Used only with highlight=True."""
    out = []
    texts = [w["text"] for w in cue.words]
    for i, w in enumerate(cue.words):
        coloured = [
            f"{{\\c{COBALT}}}{_escape(t)}{{\\c{WHITE}}}" if j == i else _escape(t)
            for j, t in enumerate(texts)
        ]
        # wrap on the plain words so widths match the non-highlighted layout
        plain_lines = _wrap(texts, max_chars)
        rendered, k = [], 0
        for line in plain_lines:
            count = len(line.split())
            rendered.append(" ".join(coloured[k : k + count]))
            k += count
        end = cue.words[i + 1]["start"] if i + 1 < len(cue.words) else w["end"]
        out.append(
            f"Dialogue: 0,{format_ass_time(w['start'] - (cue.words[0]['start'] - cue.start))},"
            f"{format_ass_time(end - (cue.words[0]['start'] - cue.start))},Clip,,0,0,0,,"
            + "\\N".join(rendered)
        )
    return out


def to_ass(
    cues: list[Cue],
    width: int = 1080,
    height: int = 1920,
    font: str = "Inter",
    font_size: int = 64,
    margin_bottom: int = 420,
    highlight: bool = False,
    max_chars: int = 38,
) -> str:
    """ASS document; MarginV keeps the text above the bottom safe area."""
    style_format = (
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    style = (
        f"Style: Clip,{font},{font_size},{WHITE},{COBALT},{INK},{INK},-1,0,0,0,100,100,0,0,1,3,0,"
        f"2,60,60,{margin_bottom},1"
    )
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        f"[V4+ Styles]\n{style_format}\n{style}\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events: list[str] = []
    for cue in cues:
        if highlight and cue.words:
            events.extend(_highlighted(cue, max_chars))
        else:
            text = "\\N".join(_escape(line) for line in cue.lines)
            events.append(
                f"Dialogue: 0,{format_ass_time(cue.start)},{format_ass_time(cue.end)},"
                f"Clip,,0,0,0,,{text}"
            )
    return header + "\n".join(events) + "\n"
