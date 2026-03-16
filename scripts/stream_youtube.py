"""Stream YouTube videos into HerdFlow for testing.

Two modes:
  1. Download: Save video locally, then use FileVideoSource
  2. Stream:   Pipe yt-dlp → ffmpeg → frames directly into pipeline

Usage:
  # Download to demo_videos/
  uv run python -m scripts.stream_youtube download "https://youtube.com/watch?v=..."

  # Run pipeline with YouTube video (download + process)
  uv run python -m scripts.stream_youtube test "https://youtube.com/watch?v=..."

  # List downloaded videos
  uv run python -m scripts.stream_youtube list
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

DEMO_DIR = Path("demo_videos")


def download(url: str, name: str | None = None) -> Path:
    """Download YouTube video at 720p using yt-dlp + ffmpeg."""
    DEMO_DIR.mkdir(exist_ok=True)

    if name is None:
        # Use video ID as filename
        vid_id = url.split("v=")[-1].split("&")[0] if "v=" in url else url.split("/")[-1]
        name = f"yt_{vid_id}"

    output = DEMO_DIR / f"{name}.mp4"
    if output.exists():
        print(f"Already downloaded: {output}")
        return output

    print(f"Downloading {url} -> {output}")
    subprocess.run(
        [
            "yt-dlp",
            "-f",
            "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "--merge-output-format",
            "mp4",
            "--postprocessor-args",
            "ffmpeg:-vf scale=1280:720",
            "-o",
            str(output),
            url,
        ],
        check=True,
    )
    print(f"Downloaded: {output} ({output.stat().st_size / 1024 / 1024:.1f} MB)")
    return output


def list_videos() -> None:
    """List downloaded demo videos."""
    DEMO_DIR.mkdir(exist_ok=True)
    videos = sorted(DEMO_DIR.glob("*.mp4"))
    if not videos:
        print("No videos in demo_videos/")
        return
    for v in videos:
        size = v.stat().st_size / 1024 / 1024
        print(f"  {v.name:40s} {size:6.1f} MB")


async def test_pipeline(video_path: Path, n_frames: int = 30) -> None:
    """Run the perception pipeline on a video and print results."""
    from agent.alerts.rules import AlertRuleEngine
    from agent.config import settings
    from agent.perception.detector import MockDetector
    from agent.perception.scene_graph import SceneGraphBuilder
    from agent.perception.tracker import Tracker
    from agent.perception.video_source import FileVideoSource

    vs = FileVideoSource(str(video_path), target_fps=2.0)
    builder = SceneGraphBuilder(
        detector=MockDetector(),
        tracker=Tracker(),
        zone_config=settings.zone_config,
        alert_engine=AlertRuleEngine(settings),
    )

    gen = vs.frames()
    prev_sg = None
    t0 = time.monotonic()

    print(f"\nProcessing {n_frames} frames from {video_path.name}...")
    for i in range(n_frames):
        frame = next(gen)
        sg = await builder.process_frame(frame, frame_id=i + 1)
        delta = builder.get_delta(prev_sg, sg)
        prev_sg = sg

        if i == 0 or (i + 1) % 10 == 0:
            hs = sg.herd_summary
            print(
                f"  Frame {i + 1:3d}: {hs.total_visible} entities | "
                f"S={hs.standing} L={hs.lying} W={hs.walking} "
                f"F={hs.feeding} D={hs.drinking} | "
                f"Alerts={len(sg.active_alerts)} | "
                f"Delta={'SIG' if delta.is_significant else 'quiet'}"
            )

    elapsed = time.monotonic() - t0
    print(f"\n  {n_frames} frames in {elapsed:.1f}s ({n_frames / elapsed:.1f} FPS)")
    vs.close()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "list":
        list_videos()
    elif cmd == "download" and len(sys.argv) >= 3:
        url = sys.argv[2]
        name = sys.argv[3] if len(sys.argv) > 3 else None
        download(url, name)
    elif cmd == "test" and len(sys.argv) >= 3:
        url_or_path = sys.argv[2]
        path = Path(url_or_path)
        if not path.exists() and url_or_path.startswith("http"):
            path = download(url_or_path)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        asyncio.run(test_pipeline(path, n))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
