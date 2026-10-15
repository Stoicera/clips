"""ffmpeg/ffprobe/yt-dlp wrappers. A local file is never written to."""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FILTERS = ("ass", "drawtext", "loudnorm")
FFMPEG_CANDIDATES = (
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",  # Homebrew: the plain `ffmpeg` bottle has no libass
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
    "/home/linuxbrew/.linuxbrew/opt/ffmpeg-full/bin/ffmpeg",
)


class ToolError(RuntimeError):
    pass


def _has_filters(binary: str) -> bool:
    try:
        out = subprocess.run(
            [binary, "-hide_banner", "-filters"], capture_output=True, text=True
        ).stdout
    except OSError:
        return False
    names = {
        line.split()[1]
        for line in out.splitlines()
        if line.startswith(" ") and len(line.split()) > 2
    }
    return all(f in names for f in REQUIRED_FILTERS)


@functools.cache
def ffmpeg() -> str:
    """First ffmpeg that has libass and drawtext: $CLIPS_FFMPEG, ffmpeg-full kegs, then PATH."""
    candidates = [
        os.environ.get("CLIPS_FFMPEG", ""),
        *FFMPEG_CANDIDATES,
        shutil.which("ffmpeg") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file() and _has_filters(c):
            return c
    raise ToolError(
        "no ffmpeg with the filters ass, drawtext and loudnorm found. "
        "Mac: brew install ffmpeg-full · Debian/Ubuntu: apt install ffmpeg · "
        "or set CLIPS_FFMPEG=/path/to/ffmpeg"
    )


def ffprobe() -> str:
    sibling = Path(ffmpeg()).with_name("ffprobe")
    return str(sibling) if sibling.is_file() else (shutil.which("ffprobe") or "ffprobe")


def require(*tools: str) -> None:
    missing = [t for t in tools if t not in ("ffmpeg", "ffprobe") and shutil.which(t) is None]
    if missing:
        raise ToolError(f"missing on PATH: {', '.join(missing)} (see README, Installation)")
    if "ffmpeg" in tools or "ffprobe" in tools:
        ffmpeg()


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise ToolError(f"{cmd[0]} failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return proc


@dataclass
class Probe:
    duration: float
    width: int
    height: int
    fps: str
    has_audio: bool

    @property
    def portrait(self) -> bool:
        return self.height > self.width


def probe(path: Path) -> Probe:
    out = run(
        [
            ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    ).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise ToolError(f"no video stream in {path}")
    return Probe(
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=video.get("r_frame_rate", "30/1"),
        has_audio=any(s.get("codec_type") == "audio" for s in data["streams"]),
    )


def extract_wav16k(src: Path, dst: Path) -> Path:
    if not dst.exists():
        run(
            [
                ffmpeg(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(dst),
            ]
        )
    return dst


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def fetch_url(url: str, into: Path) -> Path:
    """Best available quality up to 1080p as MP4; returns the downloaded file."""
    into.mkdir(parents=True, exist_ok=True)
    template = str(into / "%(id)s.%(ext)s")
    run(
        [
            "yt-dlp",
            "-f",
            "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "--merge-output-format",
            "mp4",
            "-o",
            template,
            url,
        ]
    )
    files = sorted(into.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise ToolError("yt-dlp produced no mp4")
    return files[-1]


def slugify(text: str, max_len: int = 48) -> str:
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "clip"


def frame_png(video: Path, at: float, dst: Path) -> Path:
    run(
        [
            ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{at:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(dst),
        ]
    )
    return dst


def measure_loudness(video: Path) -> dict:
    """Integrated loudness via a loudnorm analysis pass (JSON at the end of stderr)."""
    proc = subprocess.run(
        [
            ffmpeg(),
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    m = re.search(r"\{.*\}", proc.stderr, re.S)
    if not m:
        raise ToolError("loudnorm analysis produced no JSON")
    return json.loads(m.group(0))
