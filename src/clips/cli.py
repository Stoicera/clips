"""`clips` command line: run (everything) or transcribe | select | render | captions.

Everything for one recording lands in out/<YYYY-MM-DD>_<slug>/. Existing artefacts are
reused unless --force is given. Nothing is uploaded; the model only sees the transcript text.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from clips import media
from clips.captions_ass import build_cues, to_ass
from clips.config import Config, load_config
from clips.llm import ModelError, complete, extract_json
from clips.prompts import SELECT_SYSTEM, TEXTS_SYSTEM, select_prompt, texts_prompt
from clips.render import parse_crop, render_clip
from clips.select import Candidate, cut_points, validate_candidates
from clips.transcribe import transcribe
from clips.transcript import to_markdown, to_srt


class Job:
    """Paths and cached artefacts of one recording."""

    def __init__(self, source: Path, out_root: Path, force: bool) -> None:
        self.source = source
        self.force = force
        slug = media.slugify(source.stem)
        self.dir = out_root / f"{dt.date.today().isoformat()}_{slug}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "clips").mkdir(exist_ok=True)
        self.probe = media.probe(source)

    def path(self, name: str) -> Path:
        return self.dir / name

    def fresh(self, name: str) -> bool:
        return self.force or not self.path(name).exists()

    def read_json(self, name: str) -> dict:
        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def write_json(self, name: str, data) -> None:
        self.path(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- stages


def stage_transcribe(job: Job, cfg: Config) -> dict:
    if not job.fresh("transcript.json"):
        print(f"transcript.json exists, reused ({job.path('transcript.json')})")
        return job.read_json("transcript.json")
    media.require("ffmpeg", "ffprobe")
    wav = media.extract_wav16k(job.source, job.path("audio16k.wav"))
    print(f"transcribing with {cfg.whisper.backend} / {cfg.whisper.model} …")
    tr = transcribe(wav, cfg.whisper, job.dir)
    job.write_json("transcript.json", tr)
    job.path("transcript.srt").write_text(to_srt(tr["sentences"]), encoding="utf-8")
    job.path("transcript.md").write_text(to_markdown(tr["sentences"]), encoding="utf-8")
    print(f"{len(tr['words'])} words, {len(tr['sentences'])} sentences, {tr['duration']:.0f} s")
    return tr


def _candidates(raw: dict) -> tuple[list[Candidate], list[dict]]:
    cands = []
    for c in raw.get("clips", []):
        cands.append(
            Candidate(
                start_sentence=int(c["start_sentence"]),
                end_sentence=int(c["end_sentence"]),
                title=str(c.get("title", "")),
                hook=str(c.get("hook", "")),
                thesis=str(c.get("thesis", "")),
                why=str(c.get("why", "")),
            )
        )
    return cands, list(raw.get("dropped", []))


def stage_select(job: Job, cfg: Config, tr: dict) -> list[dict]:
    if not job.fresh("clips.json"):
        print("clips.json exists, reused")
        return job.read_json("clips.json")["clips"]
    sentences = tr["sentences"]
    print(f"selecting clips with {cfg.model.provider} / {cfg.model.name} …")
    prompt = select_prompt(
        sentences, cfg.min_clips, cfg.max_clips, cfg.min_clip_seconds, cfg.max_clip_seconds
    )
    answer = complete(cfg.model, SELECT_SYSTEM, prompt)
    job.path("select.raw.json").write_text(answer, encoding="utf-8")
    cands, model_dropped = _candidates(extract_json(answer))
    clips, rejected = validate_candidates(
        cands, sentences, cfg.min_clip_seconds, cfg.max_clip_seconds, cfg.max_clips
    )
    for clip in clips:
        clip.start, clip.end = cut_points(clip, sentences, job.probe.duration)
    data = {
        "source": str(job.source),
        "clips": [c.to_dict() for c in clips],
        "rejected": [{"candidate": c.__dict__, "reason": r} for c, r in rejected],
        "dropped_by_model": model_dropped,
    }
    job.write_json("clips.json", data)
    print(f"{len(clips)} clips accepted, {len(rejected)} rejected by the validator")
    if len(clips) < cfg.min_clips:
        print(f"warning: fewer than {cfg.min_clips} clips; see report.md", file=sys.stderr)
    return data["clips"]


def _words_in(tr: dict, start: float, end: float) -> list[dict]:
    return [w for w in tr["words"] if w["start"] >= start - 0.05 and w["end"] <= end + 0.05]


def stage_render(
    job: Job, cfg: Config, tr: dict, clips: list[dict], crop: str, highlight: bool
) -> list[dict]:
    media.require("ffmpeg", "ffprobe")
    region = parse_crop(crop, job.probe)
    results = []
    for clip in clips:
        name = f"{clip['index']:02d}_{media.slugify(clip['title'])}"
        ass_file = job.path(f"clips/{name}.ass")
        mp4 = job.path(f"clips/{name}.mp4")
        if job.fresh(f"clips/{name}.ass"):
            cues = build_cues(_words_in(tr, clip["start"], clip["end"]), offset=clip["start"])
            ass_file.write_text(
                to_ass(
                    cues,
                    cfg.render.width,
                    cfg.render.height,
                    cfg.render.font,
                    cfg.render.font_size,
                    cfg.render.safe_bottom,
                    highlight,
                ),
                encoding="utf-8",
            )
        if job.fresh(f"clips/{name}.mp4"):
            print(f"rendering {name} ({clip['duration']:.1f} s) …")
            render_clip(
                job.source,
                clip["start"],
                clip["end"],
                ass_file,
                mp4,
                cfg.render,
                job.probe,
                region,
                clip["title"],
            )
        results.append(_check(mp4, cfg) | {"index": clip["index"], "file": str(mp4)})
    return results


def _check(mp4: Path, cfg: Config) -> dict:
    p = media.probe(mp4)
    loud = media.measure_loudness(mp4)
    return {
        "duration": round(p.duration, 2),
        "size": f"{p.width}x{p.height}",
        "audio": p.has_audio,
        "loudness_i": float(loud["input_i"]),
        "ok": (
            cfg.min_clip_seconds - 1 <= p.duration <= cfg.max_clip_seconds + 1
            and (p.width, p.height) == (cfg.render.width, cfg.render.height)
            and p.has_audio
            and abs(float(loud["input_i"]) - cfg.render.loudness_i) <= 1.0
        ),
    }


def stage_captions(job: Job, cfg: Config, clips: list[dict]) -> None:
    if not job.fresh("captions.md"):
        print("captions.md exists, reused")
        return
    print(f"writing captions.md with {cfg.model.provider} / {cfg.model.name} …")
    answer = complete(cfg.model, TEXTS_SYSTEM, texts_prompt(clips))
    job.path("captions.raw.json").write_text(answer, encoding="utf-8")
    texts = {int(t["index"]): t for t in extract_json(answer).get("clips", [])}
    md = [
        f"# Texte je Plattform — {job.source.name}\n",
        "Status: Entwurf. Vor dem Posten lesen und kürzen.\n",
    ]
    for c in clips:
        t = texts.get(c["index"], {})
        md.append(f"\n## Clip {c['index']:02d} — {c['title']} ({c['duration']:.0f} s)\n")
        md.append(f"These: {c['thesis']}\n")
        md.append(
            f"\n### YouTube Short\n\nTitel: {t.get('youtube_title', '')}\n\n"
            f"{t.get('youtube_description', '')}\n"
        )
        md.append(f"\n### LinkedIn\n\n{t.get('linkedin', '')}\n")
        md.append(f"\n### Instagram\n\n{t.get('instagram', '')}\n")
    job.path("captions.md").write_text("\n".join(md), encoding="utf-8")


def write_report(job: Job, cfg: Config, tr: dict, clips_data: dict, checks: list[dict]) -> None:
    lines = [
        f"# Lauf {dt.datetime.now().isoformat(timespec='minutes')}\n",
        f"Quelle: `{job.source}` · {job.probe.width}x{job.probe.height} · "
        f"{job.probe.duration:.0f} s\n",
        f"Transkription: {tr.get('backend')} / {tr.get('model')} · {len(tr['words'])} Wörter\n",
        f"Modell: {cfg.model.provider} / {cfg.model.name}\n",
        "\n## Clips\n",
        "| Nr | Titel | Dauer | Größe | Lautheit (LUFS) | Prüfung |",
        "|---|---|---|---|---|---|",
    ]
    by_index = {c["index"]: c for c in checks}
    for c in clips_data["clips"]:
        k = by_index.get(c["index"])
        if k is None:
            lines.append(f"| {c['index']:02d} | {c['title']} | — | — | — | nicht gerendert |")
            continue
        lines.append(
            f"| {c['index']:02d} | {c['title']} | {k['duration']} s | {k['size']} | "
            f"{k['loudness_i']} | {'ok' if k['ok'] else 'prüfen'} |"
        )
    lines.append("\n## Verworfen\n")
    for r in clips_data.get("rejected", []):
        c = r["candidate"]
        lines.append(
            f"- Sätze {c['start_sentence']}–{c['end_sentence']} „{c['title']}“: {r['reason']}"
        )
    for d in clips_data.get("dropped_by_model", []):
        lines.append(
            f"- Sätze {d.get('start_sentence')}–{d.get('end_sentence')} (Modell): {d.get('reason')}"
        )
    job.path("report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- entry point


def _resolve_source(value: str, out_root: Path) -> Path:
    if media.is_url(value):
        media.require("yt-dlp")
        return media.fetch_url(value, out_root / "_downloads")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise media.ToolError(f"not a file: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="clips", description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["run", "transcribe", "select", "render", "captions"])
    ap.add_argument("input", help="recording (mp4/mov) or YouTube URL")
    ap.add_argument("--out", default="out", help="output root (default: ./out)")
    ap.add_argument(
        "--config",
        type=Path,
        help="clips.toml (default: ./clips.toml or ~/.config/clips/clips.toml)",
    )
    ap.add_argument("--force", action="store_true", help="recompute even if artefacts exist")
    ap.add_argument(
        "--crop", default="auto", help="auto | none | x:y:w:h (speaker region in the source)"
    )
    ap.add_argument(
        "--highlight", action="store_true", help="word-by-word highlighting in the subtitles"
    )
    ap.add_argument(
        "--only", type=int, help="render only this clip number (for checking clip 01 first)"
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _main(args)
    except (media.ToolError, ModelError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _main(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    out_root = Path(args.out).expanduser().resolve()
    job = Job(_resolve_source(args.input, out_root), out_root, args.force)
    print(f"→ {job.dir}")
    tr = stage_transcribe(job, cfg)
    if args.stage == "transcribe":
        return 0
    clips = stage_select(job, cfg, tr)
    if args.stage == "select":
        return 0
    if args.stage in ("run", "render"):
        subset = [c for c in clips if args.only is None or c["index"] == args.only]
        checks = stage_render(job, cfg, tr, subset, args.crop, args.highlight)
        write_report(job, cfg, tr, job.read_json("clips.json"), checks)
        bad = [c for c in checks if not c["ok"]]
        print(f"rendered {len(checks)} clips, {len(bad)} need a look (report.md)")
    if args.stage in ("run", "captions"):
        stage_captions(job, cfg, clips)
    print(f"done → {job.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
