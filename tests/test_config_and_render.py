"""Configuration precedence, model-output parsing and crop geometry."""

from pathlib import Path

import pytest

from clips.config import load_config
from clips.llm import ModelError, extract_json
from clips.media import Probe
from clips.render import Region, loudnorm_filter, parse_crop, video_filter


def test_toml_then_env_override(tmp_path: Path, monkeypatch):
    toml = tmp_path / "clips.toml"
    toml.write_text('[model]\nprovider = "openrouter"\nname = "x/y"\n[clips]\nmax_clips = 6\n')
    monkeypatch.delenv("CLIPS_MODEL_NAME", raising=False)
    cfg = load_config(toml)
    assert cfg.model.provider == "openrouter" and cfg.model.name == "x/y" and cfg.max_clips == 6
    monkeypatch.setenv("CLIPS_MODEL_NAME", "local/model")
    assert load_config(toml).model.name == "local/model"


def test_extract_json_tolerates_fences_and_prose():
    assert extract_json('Hier:\n```json\n{"clips": []}\n```\nFertig.') == {"clips": []}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ModelError):
        extract_json("kein json")


LANDSCAPE = Probe(duration=100, width=1920, height=1080, fps="30/1", has_audio=True)
PORTRAIT = Probe(duration=100, width=1080, height=1920, fps="30/1", has_audio=True)


def test_auto_crop_centres_a_9_16_window_on_landscape_only():
    r = parse_crop("auto", LANDSCAPE)
    assert r == Region(x=657, y=0, w=606, h=1080)
    assert parse_crop("auto", PORTRAIT) is None
    assert parse_crop("none", LANDSCAPE) is None
    assert parse_crop("10:20:300:400", LANDSCAPE) == Region(10, 20, 300, 400)


def test_video_filter_order_and_ass_path(tmp_path: Path):
    from clips.config import RenderConfig

    ass = tmp_path / "01.ass"
    vf = video_filter(RenderConfig(), Region(0, 0, 606, 1080), ass, "Titel: Test", None)
    assert vf.startswith("crop=606:1080:0:0,scale=1080:1920:force_original_aspect_ratio=decrease,")
    assert "pad=1080:1920" in vf
    assert vf.endswith(f"ass='{str(ass).replace(':', chr(92) + ':')}'")
    assert "drawtext=" in vf and "Titel\\: Test" in vf


def test_loudnorm_second_pass_uses_measured_values():
    from clips.config import RenderConfig

    measured = {
        "input_i": "-20.1",
        "input_tp": "-3.0",
        "input_lra": "6.0",
        "input_thresh": "-30.5",
        "target_offset": "0.2",
    }
    f = loudnorm_filter(RenderConfig(), measured)
    assert "measured_I=-20.1" in f and "linear=true" in f
    assert loudnorm_filter(RenderConfig(), None) == "loudnorm=I=-14.0:TP=-1.5:LRA=11.0"


def test_pre_gain_adds_headroom_and_limits_at_true_peak():
    from clips.config import RenderConfig
    from clips.render import pre_gain_filter

    f = pre_gain_filter(RenderConfig(), raw_input_i=-18.4)
    assert f.startswith("volume=5.40dB,alimiter=limit=0.8414")
    assert pre_gain_filter(RenderConfig(), raw_input_i=-13.5) is None
    assert "volume=20.00dB" in pre_gain_filter(RenderConfig(), raw_input_i=-60.0)
