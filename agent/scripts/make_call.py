"""Trigger an outbound call to the VERIFIED_PHONE_NUMBER.

Usage:
  uv run python -m scripts.make_call
  uv run python -m scripts.make_call +919876543210
"""

from __future__ import annotations

import sys

import httpx


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    api = "http://127.0.0.1:8000/calls/start"
    body = {"to": target} if target else {}

    try:
        r = httpx.post(api, json=body, timeout=15.0)
    except httpx.HTTPError as e:
        print(f"❌ Could not reach agent at {api}: {e}")
        print("Make sure `uv run uvicorn app.main:app --reload` is running.")
        return 1

    if r.status_code == 200:
        data = r.json()
        print(f"✅ Call queued")
        print(f"   to:       {data.get('to')}")
        print(f"   call_sid: {data.get('call_sid')}")
        print()
        print("Your phone should ring in 5-15 seconds.")
        print("After the Twilio trial preamble, Aria will speak.")
        return 0
    else:
        try:
            print(f"❌ Agent error ({r.status_code}): {r.json()}")
        except Exception:
            print(f"❌ Agent error ({r.status_code}): {r.text}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
