"""One-command e2e test launcher.

Generates fresh LiveKit tokens (farmer + video agent), patches test.html,
and starts the two-pipe agent architecture.

Usage:
    uv run python scripts/e2e.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Load .env ──
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(ROOT / "credentials.json"))

# ── Generate tokens ──
api_key = os.environ.get("LIVEKIT_API_KEY", "")
api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
livekit_url = os.environ.get("LIVEKIT_URL", "")

if not api_key or not api_secret:
    print("ERROR: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be in .env")
    sys.exit(1)

try:
    from livekit.api import AccessToken, VideoGrants
except ImportError:
    print("ERROR: livekit-api not installed. Run: uv add livekit-api")
    sys.exit(1)

room_name = f"hf-e2e-{int(time.time())}"

# Farmer token (for browser)
farmer_token = (
    AccessToken(api_key, api_secret)
    .with_identity("farmer")
    .with_name("Farmer (E2E)")
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

farmer_jwt = farmer_token.to_jwt()

# Video agent token
video_token = (
    AccessToken(api_key, api_secret)
    .with_identity("herdflow-video")
    .with_name("HerdFlow Video Agent")
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

video_jwt = video_token.to_jwt()

# ── Patch test.html ──
test_html = ROOT / "frontend" / "public" / "test.html"
if test_html.exists():
    content = test_html.read_text(encoding="utf-8")
    new_content = re.sub(
        r"const TOKEN = '[^']*'",
        f"const TOKEN = '{farmer_jwt}'",
        content,
    )
    test_html.write_text(new_content, encoding="utf-8")
    print(f"  Token patched into test.html")
else:
    print(f"  WARNING: {test_html} not found")

# ── Patch frontend/.env for React app ──
fe_env = ROOT / "frontend" / ".env"
fe_env.write_text(
    f"VITE_LIVEKIT_URL={livekit_url}\nVITE_LIVEKIT_TOKEN={farmer_jwt}\n",
    encoding="utf-8",
)
print(f"  Token written to frontend/.env")

print(f"\n=== E2E Ready ===")
print(f"  Room:     {room_name}")
print(f"  URL:      {livekit_url}")
print(f"  Farmer:   {farmer_jwt[:50]}...")
print(f"  Video:    {video_jwt[:50]}...")
print(f"  React:    cd frontend && npm run dev")
print(f"  test.html: file:///{test_html}")
print(f"\n  Start React frontend in another terminal, then talk.")
print(f"  Logs: {ROOT / 'logs' / 'herdflow.log'}")
print(f"\n  Starting agent...\n")

# ── Set env vars for the launcher ──
os.environ["VIDEO_AGENT_TOKEN"] = video_jwt
os.environ["LIVEKIT_ROOM"] = room_name

# ── Start launcher (spawns both voice + video) ──
subprocess.run(
    [sys.executable, "-m", "agent.main", "dev"],
    cwd=str(ROOT),
)
