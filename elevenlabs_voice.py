"""
elevenlabs_voice.py

Upgraded-voice path for the avatar pipeline:

    text script  ->  ElevenLabs TTS (mp3)  ->  upload to D-ID  ->  talking-avatar video

This demonstrates the provider-adapter design: the *video* step is unchanged
(same D-ID render + poll + download from generate_avatar_video.py); only the
*voice* provider is swapped from D-ID's built-in Microsoft TTS to ElevenLabs
for higher-quality / custom voices.

Auth (both read from the environment, never hard-coded):
    ELEVENLABS_API_KEY   from https://elevenlabs.io -> Profile -> API key
    DID_API_KEY          from https://studio.d-id.com -> API keys

Usage:
    export ELEVENLABS_API_KEY="..."   # PowerShell: $env:ELEVENLABS_API_KEY="..."
    export DID_API_KEY="..."
    python elevenlabs_voice.py --text "Your script here" --out output_elevenlabs.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from generate_avatar_video import DEFAULT_IMAGE, DEFAULT_TEXT, DIDClient

ELEVEN_BASE = "https://api.elevenlabs.io/v1"

# "Sarah" — a default account voice that works on the ElevenLabs free tier.
# (Shared "library" voices like Rachel require a paid plan for API use.)
# List the voices available to your key:  GET https://api.elevenlabs.io/v1/voices
DEFAULT_ELEVEN_VOICE = "EXAVITQu4vr4xnSDxMaL"
DEFAULT_ELEVEN_MODEL = "eleven_multilingual_v2"


def elevenlabs_tts(text: str, voice_id: str, model_id: str, api_key: str) -> bytes:
    """Call ElevenLabs TTS and return MP3 audio bytes."""
    if not api_key:
        raise ValueError("Missing ElevenLabs key. Set ELEVENLABS_API_KEY.")
    payload = json.dumps({
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()
    req = urllib.request.Request(
        f"{ELEVEN_BASE}/text-to-speech/{voice_id}", data=payload, method="POST"
    )
    req.add_header("xi-api-key", api_key)
    req.add_header("accept", "audio/mpeg")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"ElevenLabs TTS {e.code}: {body}") from None


def generate(text: str, image_url: str, eleven_voice: str, eleven_model: str,
             out_path: str, eleven_key: str, did_key: str) -> str:
    print("1/5  ElevenLabs TTS (script -> mp3)...")
    audio = elevenlabs_tts(text, eleven_voice, eleven_model, eleven_key)
    local_mp3 = os.path.splitext(out_path)[0] + ".mp3"
    with open(local_mp3, "wb") as f:
        f.write(audio)
    print(f"     saved {local_mp3} ({len(audio) / 1024:.0f} KB)")

    client = DIDClient(did_key)

    print("2/5  Uploading audio to D-ID...")
    audio_url = client.upload_audio(audio)

    print("3/5  Creating talk (audio -> video render)...")
    talk_id = client.create_talk_from_audio(image_url, audio_url)
    print(f"     talk id: {talk_id}")

    print("4/5  Polling until render is complete...")
    result_url = client.poll_status(talk_id)

    print(f"5/5  Downloading video -> {out_path}")
    client.download(result_url, out_path)
    print(f"Done. Saved {out_path} ({os.path.getsize(out_path) / 1024:.0f} KB)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avatar video with an ElevenLabs voice.")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--voice", default=DEFAULT_ELEVEN_VOICE, help="ElevenLabs voice id.")
    parser.add_argument("--model", default=DEFAULT_ELEVEN_MODEL, help="ElevenLabs model id.")
    parser.add_argument("--out", default="output_elevenlabs.mp4")
    args = parser.parse_args(argv)

    try:
        generate(
            args.text, args.image, args.voice, args.model, args.out,
            os.environ.get("ELEVENLABS_API_KEY", ""),
            os.environ.get("DID_API_KEY", ""),
        )
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
