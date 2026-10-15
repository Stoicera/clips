"""ffmpeg rendering of one clip: crop/scale/pad to 1080×1920, title overlay, subtitles, loudness.

Crop modes (--crop): "auto" = centred 9:16 crop for landscape sources, no crop for portrait;
"none" = whole frame scaled to 1080 wide and padded on Ink; "x:y:w:h" = explicit region.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from clips import media
from clips.config import RenderConfig
from clips.media import Probe


@dataclass
class Region:
    x: int
    y: int
    w: int
    h: int


def parse_crop(value: str, probe: Probe) -> Region | None:
    if value == "none":
        return None
    if value == "auto":
        if probe.portrait:
            return None
        h = probe.height
        w = (h * 9 // 16) & ~1
        return Region(x=(probe.width - w) // 2, y=0, w=w, h=h)
    try:
        x, y, w, h = (int(v) for v in value.split(":"))
    except ValueError as e:
        raise media.ToolError(f"--crop expects auto, none or x:y:w:h, got {value!r}") from e
    return Region(x, y, w, h)


def _font_file(font: str) -> str | None:
    if shutil.which("fc-match") is None:
        return None
    try:
        path = media.run(["fc-match", "-f", "%{file}", f"{font}:semibold"]).stdout.strip()
    except media.ToolError:
        return None
    return path or None


def _drawtext_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def _wrap_title(title: str, max_chars: int = 22) -> list[str]:
    words, lines, line = title.split(), [], ""
    for w in words:
        if line and len(f"{line} {w}") > max_chars:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    lines.append(line)
    return lines[:3]


def video_filter(
    cfg: RenderConfig,
    region: Region | None,
    ass_file: Path,
    title: str | None,
    font_file: str | None,
) -> str:
    """Builds the -vf chain. Order: crop → scale → pad → title card → subtitles."""
    parts: list[str] = []
    if region:
        parts.append(f"crop={region.w}:{region.h}:{region.x}:{region.y}")
    parts.append(
        f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )
    parts.append(f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:color={cfg.background}")
    if title and cfg.title_card:
        t = cfg.title_seconds
        parts.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=0x0B1F3A@0.92:t=fill:enable='lt(t,{t})'")
        parts.append(
            f"drawbox=x=120:y={cfg.height // 2 + 60}:w=180:h=8:color=0x2558E8:t=fill:"
            f"enable='lt(t,{t})'"
        )
        font = f"fontfile='{font_file}':" if font_file else "font='Inter':"
        for i, line in enumerate(_wrap_title(title)):
            parts.append(
                f"drawtext={font}text='{_drawtext_escape(line)}':fontcolor=white:fontsize=84:"
                f"x=120:y={cfg.height // 2 - 260 + i * 104}:enable='lt(t,{t})':"
                f"alpha='if(lt(t,{t - 0.4}),1,({t}-t)/0.4)'"
            )
    ass = str(ass_file).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    parts.append(f"ass='{ass}'")
    return ",".join(parts)


def loudnorm_filter(cfg: RenderConfig, measured: dict | None) -> str:
    base = f"loudnorm=I={cfg.loudness_i}:TP={cfg.loudness_tp}:LRA={cfg.loudness_lra}"
    if not measured:
        return base
    return (
        f"{base}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )


def pre_gain_filter(cfg: RenderConfig, raw_input_i: float, headroom_db: float = 1.0) -> str | None:
    """Make-up gain plus a true-peak limiter so peaky sources can reach the target loudness.

    loudnorm alone holds back gain to respect TP; the limiter takes the peaks first.
    """
    if cfg.loudness_i - raw_input_i <= 0.1:
        return None  # already at or above the target: loudnorm alone brings it down
    gain = min(cfg.loudness_i - raw_input_i + headroom_db, 20.0)
    limit = 10 ** (cfg.loudness_tp / 20)
    return f"volume={gain:.2f}dB,alimiter=limit={limit:.4f}:attack=5:release=80:level=false"


def _measure_segment(
    src: Path, start: float, end: float, cfg: RenderConfig, pre: str | None = None
) -> dict | None:
    """loudnorm analysis pass on the audio of this segment only (after `pre`, if given)."""
    proc = media.subprocess.run(
        [
            media.ffmpeg(),
            "-hide_banner",
            "-nostats",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-vn",
            "-af",
            (pre + "," if pre else "")
            + f"loudnorm=I={cfg.loudness_i}:TP={cfg.loudness_tp}:LRA={cfg.loudness_lra}:"
            "print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    m = media.re.search(r"\{.*\}", proc.stderr, media.re.S)
    if not m:
        return None
    data = json.loads(m.group(0))
    if data.get("input_i") in (None, "-inf"):
        return None
    return data


def render_clip(
    src: Path,
    start: float,
    end: float,
    ass_file: Path,
    out: Path,
    cfg: RenderConfig,
    probe: Probe,
    region: Region | None,
    title: str | None,
) -> Path:
    """Re-encodes the segment so the cut lands exactly on `start` (no keyframe drift)."""
    raw = _measure_segment(src, start, end, cfg)
    pre = pre_gain_filter(cfg, float(raw["input_i"])) if raw else None
    measured = _measure_segment(src, start, end, cfg, pre) if pre else raw
    af = (pre + "," if pre else "") + loudnorm_filter(cfg, measured)
    vf = video_filter(cfg, region, ass_file, title, _font_file(cfg.font))
    cmd = [
        media.ffmpeg(),
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(src),
        "-vf",
        vf,
        "-af",
        af,
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-preset",
        "medium",
        "-crf",
        str(cfg.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        probe.fps,
        "-c:a",
        "aac",
        "-b:a",
        cfg.audio_bitrate,
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(tmp := out.with_name(out.stem + ".part.mp4")),
    ]
    media.run(cmd)
    tmp.replace(out)  # only a finished render carries the final name (reruns reuse it)
    return out
