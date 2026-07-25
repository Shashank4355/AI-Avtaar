# AI Avatar Pipeline — Proof of Concept

A small, verifiable pipeline that turns a **text script into a talking-avatar
video**, built as a proof of concept for an autonomous content-production
platform (n8n + OpenAI + PostgreSQL + Docker style stack).

```
text script  ->  voice (TTS)  ->  talking-avatar video (.mp4)
```

It is deliberately minimal and honest: real API calls, a real rendered video
committed to this repo, and no dependencies beyond the Python standard library.

## What's here

| File | What it does |
|------|--------------|
| `generate_avatar_video.py` | End-to-end D-ID pipeline: create talk → poll render → download MP4. Uses D-ID's built-in Microsoft Neural TTS. |
| `elevenlabs_voice.py` | Same video step, but the **voice provider is swapped** to ElevenLabs (script → ElevenLabs mp3 → upload to D-ID → video). |
| `output_video.mp4` | A real video produced by the D-ID / Microsoft TTS path. |
| `output_elevenlabs.mp4` | A real video produced by the ElevenLabs voice path. |
| `.env.example` | The two environment variables you need. |

## Design note: provider-adapter pattern

The voice step is isolated behind a tiny interface, so the speech provider can
change without touching the video-generation logic:

- **Built-in path** (`generate_avatar_video.py`) — D-ID's Microsoft Neural TTS. Fewest moving parts.
- **Upgraded path** (`elevenlabs_voice.py`) — ElevenLabs for higher-quality / custom / cloned voices, with the audio handed to the exact same D-ID render + poll + download code.

This is the same swap-a-provider structure that keeps a larger content
pipeline maintainable: TTS, image/presenter source, and rendering are
independent stages you can upgrade one at a time.

## Run it

Requires **Python 3.9+**. No `pip install` needed — standard library only.

```bash
# 1. Set your key (never commit it)
export DID_API_KEY="your_d-id_key"          # PowerShell: $env:DID_API_KEY="..."

# 2. Generate a video from the default script
python generate_avatar_video.py

# 3. Or your own script / face image / output name
python generate_avatar_video.py --text "Hello from the pipeline." --out demo.mp4
```

For the ElevenLabs voice path:

```bash
export ELEVENLABS_API_KEY="your_elevenlabs_key"
export DID_API_KEY="your_d-id_key"
python elevenlabs_voice.py --text "Higher-quality voice demo."
```

> On the ElevenLabs **free** tier the API can only use your account's default
> voices, not shared "library" voices. The default here (`Sarah`) works on free
> accounts. List yours with `GET https://api.elevenlabs.io/v1/voices` and pass
> `--voice <id>`.

## Security

- API keys are read from **environment variables only** — never hard-coded, never written to disk, never committed. `.env` is git-ignored.
- Any key used during development should be **rotated** in the provider dashboard afterward.

## Scope & honesty

This is a focused proof of concept, not a finished product. It demonstrates
the core avatar-generation loop working against live APIs. Not yet included:
scripting/LLM stage, scheduling/orchestration (n8n), a database, multi-platform
publishing, or a presenter-image library — all straightforward next stages that
plug into the same staged design.

## Walkthrough

<!-- Add the 2–3 min screen-recording link here once recorded -->
_Video walkthrough: (link coming)_
