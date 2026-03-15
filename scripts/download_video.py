"""Download demo cattle footage from Pexels free stock video.

Usage: uv run python scripts/download_video.py

Downloads Creative Commons cattle/livestock footage for demo purposes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Pexels free stock videos — cattle/livestock
# These are placeholder URLs; replace with actual Pexels video download links
VIDEOS: list[dict[str, str]] = [
    {
        "name": "cattle_grazing.mp4",
        "url": "https://www.pexels.com/video/854783/download/",
        "description": "Cattle grazing in a field",
    },
    {
        "name": "cows_feeding.mp4",
        "url": "https://www.pexels.com/video/4823046/download/",
        "description": "Cows at a feeding trough",
    },
]

OUTPUT_DIR = Path("demo_videos")


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    for video in VIDEOS:
        filepath = OUTPUT_DIR / video["name"]
        if filepath.exists():
            print(f"Skipping {video['name']} (already exists)")
            continue
        print(f"Downloading {video['name']} — {video['description']}...")
        try:
            subprocess.run(
                ["curl", "-L", "-o", str(filepath), video["url"]],
                check=True,
            )
            print(f"  Saved to {filepath}")
        except subprocess.CalledProcessError as e:
            print(f"  Failed: {e}")


if __name__ == "__main__":
    main()
