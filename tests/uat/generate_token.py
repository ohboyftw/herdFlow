"""Generate a fresh LiveKit participant token for e2e testing.

Run: uv run python tests/uat/generate_token.py
Outputs: JWT token valid for 6 hours.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

api_key = os.environ.get("LIVEKIT_API_KEY", "")
api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
livekit_url = os.environ.get("LIVEKIT_URL", "")

if not api_key or not api_secret:
    print("ERROR: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set in .env")
    sys.exit(1)

try:
    from livekit.api import AccessToken, VideoGrants
except ImportError:
    print("ERROR: livekit-api not installed. Run: uv add livekit-api")
    sys.exit(1)

import time  # noqa: E402

room_name = f"hf-e2e-{int(time.time())}"

token = (
    AccessToken(api_key, api_secret)
    .with_identity("farmer")
    .with_name("Farmer (E2E Test)")
    .with_grants(
        VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
    )
    .with_ttl(timedelta(hours=6))
)

jwt = token.to_jwt()

print("\n=== LiveKit E2E Test Token ===")
print(f"  Room:     {room_name}")
print("  Identity: farmer")
print(f"  URL:      {livekit_url}")
print("  TTL:      6 hours")
print(f"\n  Token:\n  {jwt}")
print("\n  Paste into test.html TOKEN constant, or use with React frontend.")
