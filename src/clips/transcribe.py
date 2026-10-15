"""Transcription backends. Both return the shape documented in clips.transcript.

whisper-cpp     `whisper-cli` from Homebrew/apt or a source build, model from ~/.cache/clips/models
faster-whisper  optional extra; CTranslate2 on CPU or CUDA, model pulled from Hugging Face once
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from clips import media
from clips.config import WhisperConfig
from clips.transcript import sentences_from_words

MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model}.bin"


def transcribe(wav: Path, cfg: WhisperConfig, workdir: Path) -> dict:
    if cfg.backend == "whisper-cpp":
        words = _whisper_cpp(wav, cfg, workdir)
    elif cfg.backend == "faster-whisper":
        words = _faster_whisper(wav, cfg)
    else:
        raise media.ToolError(f"unknown whisper backend: {cfg.backend}")
    words = [w for w in words if w["text"] and w["end"] >= w["start"]]
    sentences = sentences_from_words(words)
    return {
        "language": cfg.language,
        "backend": cfg.backend,
        "model": cfg.model,
        "duration": words[-1]["end"] if words else 0.0,
        "words": words,
        "sentences": sentences,
    }


def ensure_model(cfg: WhisperConfig) -> Path:
    path = cfg.model_dir / f"ggml-{cfg.model}.bin"
    if path.exists():
        return path
    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    url = MODEL_URL.format(model=cfg.model)
    print(f"downloading {url} → {path} (once)")
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(path)
    return path


def _whisper_cpp(wav: Path, cfg: WhisperConfig, workdir: Path) -> list[dict]:
    media.require("whisper-cli")
    model = ensure_model(cfg)
    prefix = workdir / "whisper"
    media.run(
        [
            "whisper-cli",
            "-m",
            str(model),
            "-l",
            cfg.language,
            "-t",
            str(cfg.threads),
            "-ml",
            "1",
            "-sow",
            "-ojf",
            "-np",
            "-of",
            str(prefix),
            "-f",
            str(wav),
        ]
    )
    data = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
    words = []
    for seg in data["transcription"]:
        text = seg["text"].strip()
        if not text or text.startswith("[") or text.startswith("("):
            continue  # [_BEG_], [Musik], (Applaus)
        words.append(
            {
                "text": text,
                "start": seg["offsets"]["from"] / 1000,
                "end": seg["offsets"]["to"] / 1000,
            }
        )
    return words


def _faster_whisper(wav: Path, cfg: WhisperConfig) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise media.ToolError("faster-whisper not installed: uv sync --extra faster-whisper") from e
    model = WhisperModel(
        cfg.model, device="auto", compute_type="auto", download_root=str(cfg.model_dir)
    )
    segments, _ = model.transcribe(
        str(wav), language=cfg.language, word_timestamps=True, vad_filter=True
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"text": w.word.strip(), "start": float(w.start), "end": float(w.end)})
    return words
