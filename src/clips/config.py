"""Configuration: clips.toml (cwd, then ~/.config/clips/clips.toml), overridable by env.

Swapping the model is one line under [model]; no provider is wired into code paths.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL_DIR = Path.home() / ".cache" / "clips" / "models"


@dataclass
class ModelConfig:
    provider: str = "anthropic"  # anthropic | openrouter | openai-compatible
    name: str = "claude-opus-5-5"
    base_url: str = (
        ""  # openrouter: https://openrouter.ai/api/v1 · ollama: http://localhost:11434/v1
    )
    api_key_env: str = "ANTHROPIC_API_KEY"
    effort: str = "medium"  # anthropic only: low | medium | high | xhigh | max
    workspace_id: str = ""  # anthropic only: needed when the key is not scoped to a workspace
    max_tokens: int = 16000


@dataclass
class WhisperConfig:
    backend: str = "whisper-cpp"  # whisper-cpp | faster-whisper
    model: str = "large-v3-turbo"
    model_dir: Path = DEFAULT_MODEL_DIR
    language: str = "de"
    threads: int = 4


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    crf: int = 20
    audio_bitrate: str = "192k"
    loudness_i: float = -14.0
    loudness_tp: float = -1.5
    loudness_lra: float = 11.0
    font: str = "Inter"
    font_size: int = 64
    safe_top: int = 240
    safe_bottom: int = 420
    background: str = "0x111827"  # Ink
    title_card: bool = True
    title_seconds: float = 2.0


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    min_clip_seconds: float = 20.0
    max_clip_seconds: float = 60.0
    max_clips: int = 8
    min_clips: int = 5
    source: Path | None = None


def _apply(section: object, values: dict) -> None:
    for key, value in values.items():
        if hasattr(section, key):
            current = getattr(section, key)
            setattr(section, key, Path(value).expanduser() if isinstance(current, Path) else value)


def load_config(explicit: Path | None = None) -> Config:
    cfg = Config()
    candidates = (
        [explicit]
        if explicit
        else [Path("clips.toml"), Path.home() / ".config" / "clips" / "clips.toml"]
    )
    for path in candidates:
        if path and path.is_file():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            _apply(cfg.model, data.get("model", {}))
            _apply(cfg.whisper, data.get("whisper", {}))
            _apply(cfg.render, data.get("render", {}))
            _apply(cfg, data.get("clips", {}))
            cfg.source = path
            break
    _apply_env(cfg)
    return cfg


_ENV_MAP = {
    "CLIPS_MODEL_PROVIDER": ("model", "provider"),
    "CLIPS_MODEL_NAME": ("model", "name"),
    "CLIPS_MODEL_BASE_URL": ("model", "base_url"),
    "CLIPS_MODEL_API_KEY_ENV": ("model", "api_key_env"),
    "ANTHROPIC_WORKSPACE_ID": ("model", "workspace_id"),
    "CLIPS_WHISPER_BACKEND": ("whisper", "backend"),
    "CLIPS_WHISPER_MODEL": ("whisper", "model"),
    "CLIPS_MODEL_DIR": ("whisper", "model_dir"),
}


def _apply_env(cfg: Config) -> None:
    for var, (section, key) in _ENV_MAP.items():
        if value := os.environ.get(var):
            _apply(getattr(cfg, section), {key: value})
