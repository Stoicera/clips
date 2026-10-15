# Clips — Agent Context


## Company (Stoicera Software Group)

Two founders (Sebastian Kern, Raphael Lugmayr), Upper Austria. Brands: Stoicera (B2B web/AI/EU cloud, modern stack) and Lugmayr-Kern (.NET/Java contract work, B2C). Goal until 7.7.2027: 10,000 € monthly result, half recurring — every task names the goal it serves; results first, ship the 80 % version, measure, iterate. Founders orchestrate; agents build, test, deploy, operate. Truth before effect: no invented facts, no superlatives, name assumptions. Simple over complete. Decide and report in three lines (done, open, blocked). Customer contact answered substantively within 4 hours. Never: customer data or secrets in repo/prompts; dark patterns; religious or warrior vocabulary in anything public; Hostinger/Vercel/Railway. German (AT) for customers, code in English, commits in German.

## What Clips is

One sentence: turns one long recording into 5–8 vertical clips with burnt-in subtitles, an SRT file and platform texts, for the Stoicera channels (K7). Spec: SSOT `ai/prompts/video-to-clips.md`; how it works: `README.md`.
Non-goals:
- Posting, scheduling or uploading anything — a human posts natively.
- Any cloud processing of faces or voices — whisper.cpp and ffmpeg run locally; only transcript text reaches the configured model.
- A video editor — fine cutting is DaVinci Resolve's job; this repo produces the 80 % version.
No PRD yet; the SSOT prompt is the spec.

## How we work here

- Work = GitHub issue. Questions as issue comments, not chat.
- Fresh git worktree per task from `origin/main` (never build on main), PR against `main` with `Closes #NN` and the template Intent · Gherkin · Evidence · Debt taken · Open. Small PRs. CI green before PR. Full loop: `ai/prompts/factory-feature.md`.
- Build: `uv sync --all-groups` · Test: `uv run pytest --cov` · Lint: `uv run ruff check . && uv run ruff format --check .` · all three: `just test`. Migrate: none (no database).
- Deploy: none. This is a local command-line tool; `deploy.yml` stays inactive (no `COOLIFY_APP_UUID`). Gate: `direct`.
- Preview: none. Evidence per PR is a rendered run (`report.md`, frames of clip 01).
- Before you request review: check the result against the intent, fix deviations yourself. Copilot review runs automatically on every PR; a second model reviews security.
- Decisions with reach → `docs/decisions/` (ADR, one page). Cycle memo → `docs/cycles/`.
- After any production change: append one line to `ops/runlog.md` (date · agent · what · rollback).

## Conventions

- Stack: Python 3.11+, uv, ruff (complexity ≤ 8), pytest; ffmpeg with libass, whisper.cpp; the model behind `clips.llm.complete` is swapped in `clips.toml`, never in code.
- Times in seconds (float) everywhere; file names `NN_<slug>`; German output, English code.
- No new dependency without one sentence of justification in the PR. No speculative abstractions.
- Tests: unit for the cutting and caption logic; nothing in `tests/` needs a network, a model or ffmpeg. Synthetic recordings only (`scripts/testaufnahme.py`); never a real recording in the repo.

## Never

- Personal or customer data in repo, fixtures, logs or prompts.
- Secrets in files; use 1Password (`op run`) or Coolify secrets.
- Destructive operations (drop, force-push, rm -rf on servers) without a fresh backup and a run-log line.
- Silent scope changes: if the PRD is wrong, say so in the issue, then build.
