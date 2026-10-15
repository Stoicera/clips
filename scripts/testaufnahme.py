#!/usr/bin/env python3
"""Builds a synthetic test recording: a Markdown script read by macOS text-to-speech
over a plain 1920x1080 canvas. Used when no long real recording is at hand.

Usage: python scripts/testaufnahme.py <skript.md> <out.mp4> [--voice Anna] [--max-words N]
Needs macOS `say` and ffmpeg. The result contains no face and no real voice.
"""

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def spoken_text(markdown: str, max_words: int) -> str:
    """Keeps only spoken paragraphs: drops frontmatter, headings, tables, cues, notes."""
    body = re.sub(r"^---.*?---\s*", "", markdown, count=1, flags=re.S)
    if "## S00" in body:  # drop everything before the first scene, including its heading line
        body = body.split("## S00", 1)[-1].split("\n", 1)[-1]
    out: list[str] = []
    for para in body.split("\n\n"):
        p = para.strip()
        if not p or p.startswith(("#", "|", "*", "-", "**")):
            continue
        p = re.sub(r"\[[^\]]*\]", "", p)  # cues in square brackets are not spoken
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            out.append(p)
    words = " ".join(out).split()
    return " ".join(words[:max_words])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("skript")
    ap.add_argument("out")
    ap.add_argument("--voice", default="Anna")
    ap.add_argument("--max-words", type=int, default=1500)
    a = ap.parse_args()
    text = spoken_text(Path(a.skript).read_text(encoding="utf-8"), a.max_words)
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "speech.aiff"
        subprocess.run(["say", "-v", a.voice, "-r", "165", "-o", str(aiff), text], check=True)
        canvas = (
            "color=c=0x1f2937:s=1920x1080:r=30,"
            "drawbox=x=760:y=140:w=400:h=400:color=0xe5e7eb:t=fill,"
            "drawbox=x=560:y=560:w=800:h=520:color=0x9ca3af:t=fill"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                canvas,
                "-i",
                str(aiff),
                "-shortest",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                a.out,
            ],
            check=True,
        )
    print(f"{a.out}: {len(text.split())} words")


if __name__ == "__main__":
    main()
