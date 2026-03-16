"""File-based video source for offline/demo perception pipeline.

Reads frames from a local video file using PyAV, loops when reaching the end.
Yields numpy arrays (H, W, 3) uint8 at a configurable FPS.
"""

from __future__ import annotations

import logging
from pathlib import Path

import av

logger = logging.getLogger(__name__)


class FileVideoSource:
    """Read frames from a video file, looping infinitely."""

    def __init__(self, path: str | Path, target_fps: float = 2.0) -> None:
        self._path = Path(path)
        self._target_fps = target_fps
        self._container: av.InputContainer | None = None  # type: ignore[type-arg]
        self._stream_fps: float = 30.0
        self._skip: int = 1  # read every Nth frame

        self.loop_count: int = 0

        if not self._path.exists():
            msg = f"Video file not found: {self._path}"
            raise FileNotFoundError(msg)

    def open(self) -> None:
        """Open the video file and compute frame skip rate."""
        self._container = av.open(str(self._path))
        assert self._container is not None
        stream = self._container.streams.video[0]
        self._stream_fps = float(stream.average_rate)
        self._skip = max(1, round(self._stream_fps / self._target_fps))
        logger.info(
            "Opened %s (%dx%d @ %.1f fps, reading every %d frames → ~%.1f fps)",
            self._path.name,
            stream.width,
            stream.height,
            self._stream_fps,
            self._skip,
            self._stream_fps / self._skip,
        )

    def frames(self) -> __builtins__:  # type: ignore[name-defined]
        """Yield (H, W, 3) uint8 numpy frames, looping forever."""
        while True:
            if self._container is None:
                self.open()
            assert self._container is not None

            count = 0
            for frame in self._container.decode(video=0):
                count += 1
                if count % self._skip != 0:
                    continue
                yield frame.to_ndarray(format="rgb24")

            # Loop: seek back to start
            logger.debug("Video ended, looping %s", self._path.name)
            self._container.seek(0)

    def close(self) -> None:
        """Close the video container."""
        if self._container:
            self._container.close()
            self._container = None
