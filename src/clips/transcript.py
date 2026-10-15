"""Transcript shape shared by every backend, plus sentence splitting and SRT output.

transcript.json = {"language", "duration", "words": [...], "sentences": [...]}
word     = {"text", "start", "end"}                       (seconds, float)
sentence = {"id", "start", "end", "text", "words": [...]}
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"[.!?…]['\")»“]?$")
_ABBREVIATION = re.compile(
    r"(?:^|\s)(?:z\.B\.|bzw\.|ca\.|Nr\.|Dr\.|Mio\.|Mrd\.|u\.a\.|d\.h\.|vgl\.|[A-Za-z]\.)$"
)
_NUMBER_DOT = re.compile(r"\d\.$")


def _ends_sentence(text: str) -> bool:
    if not _SENTENCE_END.search(text):
        return False
    if _ABBREVIATION.search(text) or _NUMBER_DOT.search(text):
        return False
    return True


def sentences_from_words(
    words: list[dict], max_gap: float = 1.2, max_chars: int = 220
) -> list[dict]:
    """Groups words into sentences at punctuation, long pauses or a length cap."""
    sentences: list[dict] = []
    current: list[dict] = []

    def flush() -> None:
        if current:
            sentences.append(
                {
                    "id": len(sentences),
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "text": " ".join(w["text"] for w in current),
                    "words": list(current),
                }
            )
            current.clear()

    for word in words:
        if current and word["start"] - current[-1]["end"] > max_gap:
            flush()
        current.append(word)
        length = sum(len(w["text"]) + 1 for w in current)
        if _ends_sentence(word["text"]) or length > max_chars:
            flush()
    flush()
    return sentences


def format_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(sentences: list[dict]) -> str:
    out = []
    for n, s in enumerate(sentences, start=1):
        out.append(
            f"{n}\n{format_srt_time(s['start'])} --> {format_srt_time(s['end'])}\n{s['text']}\n\n"
        )
    return "".join(out)


def to_markdown(sentences: list[dict], paragraph_seconds: float = 45.0) -> str:
    """Readable transcript: a timestamp at the head of each paragraph."""
    lines: list[str] = []
    para: list[str] = []
    para_start = 0.0
    for s in sentences:
        if para and s["start"] - para_start >= paragraph_seconds:
            lines.append(f"**[{_mmss(para_start)}]** " + " ".join(para) + "\n")
            para = []
        if not para:
            para_start = s["start"]
        para.append(s["text"])
    if para:
        lines.append(f"**[{_mmss(para_start)}]** " + " ".join(para) + "\n")
    return "\n".join(lines)


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
