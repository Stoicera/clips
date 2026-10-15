# clips

One long recording in, short vertical clips out: transcript, 5–8 clips of 20–60 s with burnt-in
subtitles, an SRT file for YouTube and the texts for LinkedIn, Instagram and YouTube Shorts.
Everything runs on this machine. The only thing that leaves it is the transcript text, sent to
the model you configure (Anthropic, OpenRouter or a local server). No face, no voice, no upload.

Stoicera Software Group · MIT · goal served: `core/26` reach (K7, one recording → five cuts).

```bash
clips run aufnahme.mp4
```

Result in `out/<YYYY-MM-DD>_<slug>/`:

| File | What |
|---|---|
| `transcript.json` | words and sentences with timestamps (seconds) |
| `transcript.srt` | for the YouTube upload of the long video |
| `transcript.md` | readable, a timestamp per paragraph |
| `clips.json` | the chosen clips with title, thesis, why; rejected candidates with reasons |
| `clips/NN_<slug>.mp4` | 1080×1920, H.264 High, CRF 20, AAC 192 kbit/s, loudness −14 LUFS |
| `clips/NN_<slug>.ass` | the subtitles of that clip; fix a word here, rerun `clips render --force` |
| `captions.md` | per clip: YouTube Short title and description, LinkedIn (Sie), Instagram |
| `report.md` | ffprobe facts per clip, loudness, what was dropped and why |

Nothing is posted. A human watches the clips, edits the texts, posts natively.

## Installation

Needs: Python ≥ 3.11 with [uv](https://docs.astral.sh/uv/), ffmpeg with libass and freetype,
whisper.cpp (`whisper-cli`). `yt-dlp` and the Anthropic SDK come with `uv sync`.

**Mac (Apple Silicon, Homebrew):**

```bash
brew install uv ffmpeg-full whisper-cpp font-inter
git clone https://github.com/Stoicera/clips && cd clips
uv sync
uv run clips run ~/Work/stoicera/clips/in/aufnahme.mp4 --out ~/Work/stoicera/clips/out
```

The plain `ffmpeg` bottle of Homebrew (version 9) has no libass and no drawtext; `clips` looks
for `ffmpeg-full` under `/opt/homebrew/opt/ffmpeg-full/bin` first, then on `PATH`, and tells you
when none qualifies. `CLIPS_FFMPEG=/path/to/ffmpeg` overrides. whisper.cpp runs on Metal.

**Linux (Debian/Ubuntu):**

```bash
sudo apt install ffmpeg fonts-inter build-essential cmake git
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp && cmake -B build && cmake --build build -j && sudo cp build/bin/whisper-cli /usr/local/bin/
git clone https://github.com/Stoicera/clips && cd clips && uv sync
```

Without whisper.cpp, use the faster-whisper backend (CPU or CUDA):
`uv sync --extra faster-whisper` and `backend = "faster-whisper"` in `clips.toml`.

The whisper model (`ggml-large-v3-turbo.bin`, 1.6 GB) is downloaded once into
`~/.cache/clips/models/` on the first run. [mise](https://mise.jdx.dev) users: `.python-version`
is present; `mise use python@3.13 uv` and go on.

## Model and key

Copy `clips.example.toml` to `clips.toml` (working directory) or `~/.config/clips/clips.toml`.
The model is one line:

```toml
[model]
provider = "anthropic"            # anthropic | openrouter | openai-compatible
name = "claude-opus-5-5"
api_key_env = "ANTHROPIC_API_KEY"
```

OpenRouter: `provider = "openrouter"`, `name = "anthropic/claude-opus-5.5"`,
`api_key_env = "OPENROUTER_API_KEY"`. Local (Ollama, LM Studio): `provider = "openai-compatible"`,
`base_url = "http://localhost:11434/v1"`, `name = "qwen3:14b"`, no key.
Environment variables override the file: `CLIPS_MODEL_PROVIDER`, `CLIPS_MODEL_NAME`,
`CLIPS_MODEL_BASE_URL`, `CLIPS_MODEL_API_KEY_ENV`, `ANTHROPIC_WORKSPACE_ID`,
`CLIPS_WHISPER_BACKEND`, `CLIPS_WHISPER_MODEL`, `CLIPS_MODEL_DIR`, `CLIPS_FFMPEG`.

The key never goes into a file. With 1Password:

```bash
export ANTHROPIC_API_KEY="$(op read 'op://Agents/<item>/credential')"
```

## The four stages

`clips run` does all four. Each can run alone; artefacts that exist are reused unless `--force`.

| Command | Does | Writes |
|---|---|---|
| `clips transcribe <in>` | 16 kHz WAV via ffmpeg, whisper.cpp with word timestamps, German | `transcript.json/.srt/.md` |
| `clips select <in>` | one model pass over the numbered sentences, then the validator | `clips.json`, `select.raw.json` |
| `clips render <in>` | per clip: crop, scale, pad, 2 s title card, subtitles burnt in, two-pass loudnorm | `clips/*.mp4`, `clips/*.ass`, `report.md` |
| `clips captions <in>` | one model pass over the clip texts | `captions.md`, `captions.raw.json` |

`just transcribe|select|render|captions <in>` wraps the same. `<in>` is a file (never modified)
or a YouTube URL (fetched with yt-dlp at best quality ≤ 1080p).

Check the first clip before the rest: `clips render <in> --only 1`, open the MP4, read `report.md`.

### Selection rules (validator, tested)

The model proposes candidates as sentence ranges with title, hook, thesis and why. The validator
keeps a candidate only if it is 20–60 s, starts and ends on sentence boundaries, does not overlap an
earlier (higher ranked) candidate, and the total stays ≤ 8. Nothing is stretched; everything
dropped is listed in `report.md` with the reason, including what the model dropped itself
(for example a number without a date in the source).

### Crop parameters

`--crop auto` (default): a portrait source is used as it is; a landscape source gets a centred
9:16 window — the usual case for a phone on a tripod with the speaker in the middle.

```bash
clips render aufnahme.mp4 --crop 480:0:960:1080     # talking head left of centre: x:y:w:h in source pixels
clips render aufnahme.mp4 --crop none               # whole frame, scaled to 1080 wide, padded on Ink #111827
```

Pick the region with any player: note x, y, width, height of the speaker in the source.
Split screen (speaker above, screen below) is not built yet; use `--crop none` for screencasts.

### Subtitles

Built from the word timestamps: at most 2 lines of 38 characters, Inter semibold 64 px, white with
a thin Ink outline, bottom edge 420 px above the frame bottom, nothing in the top 240 px. One
`.ass` file per clip; fix a word there and rerun `clips render --force --only N`.
`--highlight` colours the spoken word in Cobalt #2558E8 (off by default).

### Sound and export

Two-pass EBU R128 loudnorm to I = −14 LUFS, TP = −1.5 dBTP, LRA = 11. A true-peak limiter runs
before the second pass so peaky sources (phones, text-to-speech) still reach the target.
MP4 1080×1920, H.264 high, yuv420p, CRF 20, AAC 192 kbit/s, `+faststart`, source frame rate.

## Development

```bash
uv sync --all-groups
just test            # ruff, format check, pytest with coverage
```

Tests cover the cutting logic (validator, cut points), subtitle cue building, sentence splitting,
configuration precedence, model-output parsing and crop geometry. Nothing in the tests needs
a network, a model or ffmpeg.

`scripts/testaufnahme.py <skript.md> <out.mp4>` builds a synthetic test recording on a Mac
(the macOS German voice reading a script over a plain canvas) when no long real recording is at hand.

## What the pipeline deliberately does not do

- Post, schedule or upload anything. Not even the SRT.
- Send audio or video anywhere. Only the transcript text reaches the model.
- Invent a date for a number. Such candidates are dropped and reported.
- Fine cutting. If a clip needs it, `report.md` says which one; a human does that pass in DaVinci Resolve.
- Split screen for screencasts, a logo on the title card, `werkbank.md`, Ghost drafts (open; see the SSOT prompt `ai/prompts/video-to-clips.md`).
