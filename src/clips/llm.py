"""One function, `complete(system, user) -> str`, behind three providers.

anthropic          official SDK (adaptive thinking, effort, retries built in)
openrouter         OpenAI-compatible chat endpoint at openrouter.ai
openai-compatible  any OpenAI-style endpoint, e.g. Ollama or LM Studio on this machine
Keys come from the environment variable named in the config (1Password: `op run`).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from clips.config import ModelConfig


class ModelError(RuntimeError):
    pass


def complete(cfg: ModelConfig, system: str, user: str) -> str:
    if cfg.provider == "anthropic":
        return _anthropic(cfg, system, user)
    if cfg.provider in ("openrouter", "openai-compatible"):
        return _openai_compatible(cfg, system, user)
    raise ModelError(f"unknown model provider: {cfg.provider}")


def _api_key(cfg: ModelConfig, required: bool) -> str:
    key = os.environ.get(cfg.key_env, "")
    if required and not key:
        raise ModelError(f"environment variable {cfg.key_env} is empty (provider {cfg.provider})")
    return key


def _anthropic(cfg: ModelConfig, system: str, user: str) -> str:
    import anthropic

    # Explicit base URL: a stray ANTHROPIC_BASE_URL in the shell must not reroute the call.
    headers = {"anthropic-workspace-id": cfg.workspace_id} if cfg.workspace_id else None
    client = anthropic.Anthropic(
        api_key=_api_key(cfg, required=True),
        base_url=cfg.base_url or "https://api.anthropic.com",
        default_headers=headers,
    )
    try:
        response = client.messages.create(
            model=cfg.name,
            max_tokens=cfg.max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": cfg.effort},
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIStatusError as e:
        raise ModelError(f"Anthropic API {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ModelError(f"Anthropic API unreachable: {e}") from e
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise ModelError(
            f"model refused: {getattr(details, 'explanation', '') or 'no explanation'}"
        )
    if response.stop_reason == "max_tokens":
        raise ModelError("model output cut at max_tokens; raise [model] max_tokens")
    return "".join(block.text for block in response.content if block.type == "text")


def _openai_compatible(cfg: ModelConfig, system: str, user: str) -> str:
    base = cfg.base_url or (
        "https://openrouter.ai/api/v1"
        if cfg.provider == "openrouter"
        else "http://localhost:11434/v1"
    )
    key = _api_key(cfg, required=cfg.provider == "openrouter")
    body = {
        "model": cfg.name,
        "max_tokens": cfg.max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if cfg.provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/Stoicera/clips"
        headers["X-Title"] = "clips"
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions", data=json.dumps(body).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ModelError(f"{cfg.provider} HTTP {e.code}: {e.read()[:300]!r}") from e
    except urllib.error.URLError as e:
        raise ModelError(f"{cfg.provider} unreachable at {base}: {e.reason}") from e
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ModelError(f"unexpected response shape from {cfg.provider}: {str(data)[:300]}") from e


def extract_json(text: str):
    """Tolerates code fences and prose around the JSON the prompt asked for."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = fenced.group(1) if fenced else text
    start = min([i for i in (raw.find("["), raw.find("{")) if i >= 0], default=-1)
    if start < 0:
        raise ModelError(f"no JSON in model output: {text[:200]!r}")
    end = max(raw.rfind("]"), raw.rfind("}"))
    return json.loads(raw[start : end + 1])
