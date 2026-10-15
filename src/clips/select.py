"""Clip selection: the model proposes candidates by sentence index, this module decides.

Rules (ai/prompts/video-to-clips.md §4): 20–60 s, no overlaps, 5–8 clips, start and end
on sentence boundaries, drop rather than stretch. Every rejection carries a reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Candidate:
    start_sentence: int
    end_sentence: int
    title: str
    hook: str = ""
    thesis: str = ""
    why: str = ""


@dataclass
class Clip:
    index: int
    start: float
    end: float
    title: str
    hook: str
    thesis: str
    why: str
    text: str
    sentences: list[int] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        return d


def _reject_reason(c: Candidate, sentences: list[dict], min_s: float, max_s: float) -> str | None:
    n = len(sentences)
    if not (0 <= c.start_sentence < n and 0 <= c.end_sentence < n):
        return f"sentence index out of range (0..{n - 1})"
    if c.end_sentence < c.start_sentence:
        return "end before start"
    dur = sentences[c.end_sentence]["end"] - sentences[c.start_sentence]["start"]
    if dur < min_s:
        return f"too short: {dur:.1f} s < {min_s:.0f} s"
    if dur > max_s:
        return f"too long: {dur:.1f} s > {max_s:.0f} s"
    return None


def validate_candidates(
    candidates: list[Candidate],
    sentences: list[dict],
    min_s: float = 20.0,
    max_s: float = 60.0,
    max_clips: int = 8,
) -> tuple[list[Clip], list[tuple[Candidate, str]]]:
    """Accepts candidates in model order (the model ranks), then sorts accepted by start."""
    accepted: list[Clip] = []
    rejected: list[tuple[Candidate, str]] = []
    for c in candidates:
        reason = _reject_reason(c, sentences, min_s, max_s)
        if reason is None and len(accepted) >= max_clips:
            reason = f"maximum of {max_clips} clips reached"
        if reason is None:
            start, end = sentences[c.start_sentence]["start"], sentences[c.end_sentence]["end"]
            if any(a.start < end and start < a.end for a in accepted):
                reason = "overlap with an earlier candidate"
        if reason is not None:
            rejected.append((c, reason))
            continue
        span = sentences[c.start_sentence : c.end_sentence + 1]
        accepted.append(
            Clip(
                index=0,
                start=span[0]["start"],
                end=span[-1]["end"],
                title=c.title.strip(),
                hook=c.hook.strip(),
                thesis=c.thesis.strip(),
                why=c.why.strip(),
                text=" ".join(s["text"] for s in span),
                sentences=[s["id"] for s in span],
            )
        )
    accepted.sort(key=lambda a: a.start)
    for i, clip in enumerate(accepted, start=1):
        clip.index = i
    return accepted, rejected


def cut_points(
    clip: Clip, sentences: list[dict], duration: float, lead: float = 0.25, tail: float = 0.4
) -> tuple[float, float]:
    """Adds a little air before and after the clip without touching neighbouring speech."""
    first, last = clip.sentences[0], clip.sentences[-1]
    prev_end = sentences[first - 1]["end"] if first > 0 else 0.0
    next_start = sentences[last + 1]["start"] if last + 1 < len(sentences) else duration
    start = max(prev_end, clip.start - lead, 0.0)
    end = min(next_start, clip.end + tail, duration)
    return round(start, 3), round(end, 3)
