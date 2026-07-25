"""
generate_avatar_video.py

Minimal, honest proof-of-concept for the NEVIE-GLOBAL AI Avatar Factory.

Pipeline:  text script  ->  voice (TTS)  ->  talking-avatar video

This module drives the D-ID Talks API end to end using only the Python
standard library (no third-party packages), so a reviewer can clone the repo
and run it with nothing but a Python 3.9+ interpreter and an API key.

The design mirrors the "provider-adapter" pattern used in the Vector Lead and
Nova ADK projects: the voice step is isolated behind a small interface so the
built-in Microsoft TTS used here can be swapped for ElevenLabs (see
elevenlabs_voice.py) without touching the video-generation logic.

Auth:   the D-ID API key is read from the DID_API_KEY environment variable.
        It is NEVER hard-coded or written to disk.

Usage:
        # PowerShell
        $env:DID_API_KEY = "your_key_here"
        python generate_avatar_video.py

        # bash / zsh
        export DID_API_KEY="your_key_here"
        python generate_avatar_video.py

        # optional overrides
        python generate_avatar_video.py --text "Custom line" --out demo.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.d-id.com"

# A neutral, D-ID-hosted sample presenter image. Any public image URL of a
# single clear face works; override with --image.
DEFAULT_IMAGE = "https://d-id-public-bucket.s3.us-west-2.amazonaws.com/alice.jpg"

DEFAULT_TEXT = (
    "Hi, I'm a proof-of-concept avatar for the NEVIE-GLOBAL content platform. "
    "This video was generated from a text script through an automated "
    "text-to-speech and video pipeline."
)

# Microsoft Neural voice used for the built-in TTS path.
DEFAULT_VOICE = "en-US-JennyNeural"


class DIDClient:
    """Tiny stdlib wrapper around the D-ID REST API."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError(
                "Missing D-ID API key. Set the DID_API_KEY environment variable."
            )
        self._auth = f"Basic {api_key}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{API_BASE}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self._auth)
        req.add_header("accept", "application/json")
        if data is not None:
            req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"D-ID API {e.code} on {method} {path}: {body}") from None

    # --- realism config -------------------------------------------------

    @staticmethod
    def _realism_config(expression: str = "neutral", intensity: float = 0.7) -> dict:
        """Free-tier settings that make the avatar look more lifelike.

        - stitch: blend the animated face back onto the FULL original photo
          (body + background stay put) instead of a cropped floating head.
        - fluent + pad_audio: smoother motion transitions, no clipped audio.
        - driver_expressions: adds a subtle facial expression / micro-motion
          so the face isn't frozen-neutral. Applies from frame 0.
        """
        config = {
            "stitch": True,
            "fluent": True,
            "pad_audio": 0.0,
            "result_format": "mp4",
        }
        if expression and expression != "none":
            config["driver_expressions"] = {
                "expressions": [
                    {"start_frame": 0, "expression": expression, "intensity": intensity}
                ]
            }
        return config

    # --- pipeline steps -------------------------------------------------

    def create_talk(self, image_url: str, text: str, voice_id: str,
                    expression: str = "neutral") -> str:
        """Kick off a talking-avatar render. Returns the talk id."""
        payload = {
            "source_url": image_url,
            "script": {
                "type": "text",
                "input": text,
                "provider": {"type": "microsoft", "voice_id": voice_id},
            },
            "config": self._realism_config(expression),
        }
        result = self._request("POST", "/talks", payload)
        talk_id = result.get("id")
        if not talk_id:
            raise RuntimeError(f"No talk id in response: {result}")
        return talk_id

    def upload_audio(self, audio_bytes: bytes, filename: str = "voice.mp3") -> str:
        """Upload raw audio to D-ID and return a hosted URL usable as audio_url.

        Uses multipart/form-data, hand-rolled so we stay dependency-free.
        """
        boundary = "----nevieboundary7MA4YWxkTrZu0gW"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="audio"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: audio/mpeg\r\n\r\n",
            audio_bytes,
            f"\r\n--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(f"{API_BASE}/audios", data=body, method="POST")
        req.add_header("Authorization", self._auth)
        req.add_header("accept", "application/json")
        req.add_header("content-type", f"multipart/form-data; boundary={boundary}")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"D-ID audio upload {e.code}: {body}") from None
        url = result.get("url")
        if not url:
            raise RuntimeError(f"No url in audio upload response: {result}")
        return url

    def create_talk_from_audio(self, image_url: str, audio_url: str,
                               expression: str = "neutral") -> str:
        """Kick off a talking-avatar render driven by a pre-rendered audio track."""
        payload = {
            "source_url": image_url,
            "script": {"type": "audio", "audio_url": audio_url},
            "config": self._realism_config(expression),
        }
        result = self._request("POST", "/talks", payload)
        talk_id = result.get("id")
        if not talk_id:
            raise RuntimeError(f"No talk id in response: {result}")
        return talk_id

    def poll_status(self, talk_id: str, timeout_s: int = 600, interval_s: int = 5) -> str:
        """Poll until the render is done. Returns the result video URL."""
        deadline = time.time() + timeout_s
        last_status = None
        while time.time() < deadline:
            info = self._request("GET", f"/talks/{talk_id}")
            status = info.get("status")
            if status != last_status:
                print(f"  status: {status}")
                last_status = status
            if status == "done":
                url = info.get("result_url")
                if not url:
                    raise RuntimeError(f"'done' but no result_url: {info}")
                return url
            if status in ("error", "rejected"):
                raise RuntimeError(f"Render failed: {info}")
            time.sleep(interval_s)
        raise TimeoutError(f"Talk {talk_id} did not finish within {timeout_s}s")

    @staticmethod
    def download(url: str, out_path: str) -> None:
        """Stream the finished MP4 to disk."""
        with urllib.request.urlopen(url, timeout=120) as resp, open(out_path, "wb") as f:
            while chunk := resp.read(64 * 1024):
                f.write(chunk)


def generate(text: str, image_url: str, voice_id: str, out_path: str, api_key: str,
             expression: str = "neutral") -> str:
    client = DIDClient(api_key)

    print("1/3  Creating talk (script -> D-ID Microsoft TTS -> video render)...")
    talk_id = client.create_talk(image_url, text, voice_id, expression)
    print(f"     talk id: {talk_id}")

    print("2/3  Polling until render is complete...")
    result_url = client.poll_status(talk_id)

    print(f"3/3  Downloading video -> {out_path}")
    client.download(result_url, out_path)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"Done. Saved {out_path} ({size_kb:.0f} KB)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a talking-avatar video with D-ID.")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Script the avatar will speak.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Public URL of the face image.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Microsoft neural voice id.")
    parser.add_argument("--out", default="output_video.mp4", help="Output MP4 path.")
    parser.add_argument("--expression", default="neutral",
                        help="Facial expression for micro-motion: "
                             "neutral | happy | surprise | serious | none")
    args = parser.parse_args(argv)

    api_key = os.environ.get("DID_API_KEY", "")
    try:
        generate(args.text, args.image, args.voice, args.out, api_key, args.expression)
    except Exception as e:  # noqa: BLE001 - surface a clean message to the CLI user
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
