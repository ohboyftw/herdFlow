"""HerdFlow launcher — spawns voice and video agent processes.

Usage: uv run python -m agent.main dev
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

# Load .env
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _generate_video_token() -> str:
    """Generate a LiveKit token for the video agent participant."""
    from livekit.api import AccessToken, VideoGrants

    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be in .env")
        sys.exit(1)

    room_name = os.environ.get("LIVEKIT_ROOM", f"hf-{int(time.time())}")
    token = (
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
    return token.to_jwt()


def main() -> None:
    """Launch voice and video agent processes."""
    video_token = _generate_video_token()

    # Environment for video process (inherits current env + adds token)
    video_env = {**os.environ, "VIDEO_AGENT_TOKEN": video_token}

    # Pass dev mode argument if provided
    args = sys.argv[1:]

    # Spawn voice agent (uses AgentServer, gets dispatched by LiveKit)
    voice_cmd = [sys.executable, "-m", "agent.voice_agent"] + args
    voice_proc = subprocess.Popen(voice_cmd, cwd=str(Path(__file__).parent.parent))

    # Spawn video agent (uses raw Room.connect)
    video_cmd = [sys.executable, "-m", "agent.video_agent"]
    video_proc = subprocess.Popen(video_cmd, cwd=str(Path(__file__).parent.parent), env=video_env)

    print(f"  Voice agent PID: {voice_proc.pid}")
    print(f"  Video agent PID: {video_proc.pid}")
    print("  Press Ctrl+C to stop both.\n")

    # Cleanup: kill both on exit
    def cleanup() -> None:
        for proc in (voice_proc, video_proc):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda *_: cleanup())

    # Wait for either to exit
    try:
        while True:
            if voice_proc.poll() is not None:
                print(f"Voice agent exited with code {voice_proc.returncode}")
                break
            if video_proc.poll() is not None:
                print(f"Video agent exited with code {video_proc.returncode}")
                break
            time.sleep(1)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
