"""
retry_demo.py

A small, self-contained demonstration of the reliability machinery that the
full platform's pipeline needs:

    - a job with explicit states (queued -> running -> done / failed / dead-letter)
    - automatic retries with exponential backoff
    - duplicate-publication prevention via a content hash
    - a per-attempt log

It is intentionally runnable WITHOUT spending any API credits: the "work" is a
flaky operation you can force to fail with --fail-first N, so you can trigger an
error live and watch the retries kick in. In the real pipeline this same
retry_with_backoff() wraps the D-ID / publishing call instead of the mock.

Usage (great for a live walkthrough):

    # succeeds first try
    python retry_demo.py --avatar ava1 --text "Hello world"

    # fails twice, then succeeds on the 3rd attempt (shows backoff + recovery)
    python retry_demo.py --avatar ava1 --text "Hello world" --fail-first 2

    # always fails -> ends in the dead-letter state after max attempts
    python retry_demo.py --avatar ava1 --text "Hello world" --fail-first 99

    # run the SAME (avatar, text) again -> blocked as a duplicate
    python retry_demo.py --avatar ava1 --text "Hello world"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

STATE_FILE = "jobs_state.json"


# --- duplicate prevention -------------------------------------------------

def content_hash(avatar_id: str, text: str) -> str:
    """Stable hash of (avatar, content). Same avatar + same script = same job."""
    return hashlib.sha256(f"{avatar_id}::{text}".encode()).hexdigest()[:16]


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# --- retry with exponential backoff ---------------------------------------

class MaxRetriesExceeded(Exception):
    pass


def retry_with_backoff(operation, max_attempts: int = 4, base_delay: float = 1.0):
    """Call operation(); on failure retry with 1s, 2s, 4s ... backoff.

    Returns the operation result, or raises MaxRetriesExceeded after the cap.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(attempt)
            print(f"    attempt {attempt}: OK")
            return result
        except Exception as e:  # noqa: BLE001 - demo wants to catch any failure
            print(f"    attempt {attempt}: FAILED ({e})")
            if attempt == max_attempts:
                raise MaxRetriesExceeded(
                    f"gave up after {max_attempts} attempts"
                ) from e
            delay = base_delay * (2 ** (attempt - 1))
            print(f"      backing off {delay:.0f}s before retry...")
            time.sleep(delay)


# --- the (mock) unit of work ----------------------------------------------

def make_flaky_operation(fail_first: int):
    """Return an operation that fails its first `fail_first` attempts, then works.

    In production this closure would instead call the real D-ID render or the
    platform publish, and a genuine transient error (rate limit, 5xx) would
    trigger the same retry path.
    """
    def operation(attempt: int) -> str:
        if attempt <= fail_first:
            raise RuntimeError("simulated transient error")
        return f"published (post_id=demo_{int(time.time())})"

    return operation


# --- the job --------------------------------------------------------------

def run_job(avatar_id: str, text: str, fail_first: int) -> None:
    state = load_state()
    key = content_hash(avatar_id, text)

    print(f"job {key}  avatar={avatar_id!r}")

    # 1. duplicate prevention
    if state.get(key, {}).get("status") == "done":
        print("  status: SKIPPED (duplicate — this content was already published)")
        return

    # 2. run with retries
    state[key] = {"avatar": avatar_id, "status": "running", "attempts": 0}
    save_state(state)
    print("  status: running")

    operation = make_flaky_operation(fail_first)
    try:
        result = retry_with_backoff(operation)
        state[key]["status"] = "done"
        state[key]["result"] = result
        print(f"  status: DONE -> {result}")
    except MaxRetriesExceeded as e:
        state[key]["status"] = "dead-letter"
        state[key]["error"] = str(e)
        print(f"  status: DEAD-LETTER ({e}) — flagged for manual reprocessing")
    finally:
        save_state(state)
        print(f"  (state persisted to {STATE_FILE})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retry / dedup reliability demo.")
    parser.add_argument("--avatar", default="ava1", help="Avatar id.")
    parser.add_argument("--text", default="Hello world", help="Content script.")
    parser.add_argument("--fail-first", type=int, default=0,
                        help="Force the first N attempts to fail (to demo retries).")
    args = parser.parse_args(argv)
    run_job(args.avatar, args.text, args.fail_first)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
