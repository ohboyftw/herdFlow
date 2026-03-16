"""RF-DETR detector wrapper and mock detector for HerdFlow."""

from __future__ import annotations

import asyncio
import logging
import random
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from agent.models import Detection

logger = logging.getLogger(__name__)

# COCO class ID for cow
_COW_CLASS_ID = 20
_COW_CLASS_NAME = "cow"

# 8 base bounding boxes spread across a 1280x720 frame (x1, y1, x2, y2)
_BASE_BBOXES: list[tuple[int, int, int, int]] = [
    (50, 80, 200, 220),
    (250, 100, 420, 260),
    (480, 60, 640, 200),
    (700, 90, 860, 230),
    (920, 70, 1080, 210),
    (100, 380, 280, 540),
    (450, 400, 630, 560),
    (800, 350, 980, 500),
]
_BASE_CONFIDENCES: list[float] = [0.92, 0.87, 0.81, 0.95, 0.76, 0.88, 0.83, 0.79]

# Maximum pixel jitter applied per call to simulate movement
_JITTER_PX = 8


class MockDetector:
    """Returns hardcoded detections for Phase 2 development.

    Each call slightly varies the bounding boxes to simulate animal movement.
    All detections have class_name='cow', class_id=20, confidence >= 0.3.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def detect_sync(self, frame: np.ndarray) -> list[Detection]:
        """Synchronous detection — returns 8 mock cow detections."""
        detections: list[Detection] = []
        for (x1, y1, x2, y2), conf in zip(_BASE_BBOXES, _BASE_CONFIDENCES, strict=True):
            jx = self._rng.randint(-_JITTER_PX, _JITTER_PX)
            jy = self._rng.randint(-_JITTER_PX, _JITTER_PX)
            bx1 = max(0, x1 + jx)
            by1 = max(0, y1 + jy)
            bx2 = max(bx1 + 1, x2 + jx)
            by2 = max(by1 + 1, y2 + jy)
            # Slightly vary confidence too (±0.03), clamp to [0.3, 1.0]
            varied_conf = max(0.3, min(1.0, conf + self._rng.uniform(-0.03, 0.03)))
            detections.append(
                Detection(
                    class_id=_COW_CLASS_ID,
                    class_name=_COW_CLASS_NAME,
                    confidence=varied_conf,
                    bbox=(bx1, by1, bx2, by2),
                )
            )
        logger.debug("[B1->B2] detect: %d detections (mock)", len(detections))
        return detections

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        """Async detection — delegates to detect_sync (mock, no GIL concern)."""
        return self.detect_sync(frame)


class RFDETRDetector:
    """RF-DETR detector with GIL-safe inference via ThreadPoolExecutor.

    Wraps the `rfdetr` package and converts supervision Detections objects
    to the HerdFlow Detection dataclass.
    """

    def __init__(self, model_name: str = "rf-detr-base", threshold: float = 0.3) -> None:
        from rfdetr import RFDETRBase  # type: ignore[import-untyped]

        self.model = RFDETRBase()
        self.threshold = threshold
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

    def detect_sync(self, frame: np.ndarray) -> list[Detection]:
        """Synchronous detection on a single frame.

        Args:
            frame: BGR or RGB numpy array (H, W, 3).

        Returns:
            List of Detection objects above the confidence threshold.
        """
        import supervision as sv  # type: ignore[import-untyped]

        sv_detections: sv.Detections = self.model.predict(frame, threshold=self.threshold)  # type: ignore[assignment]

        detections: list[Detection] = []
        if sv_detections is None or len(sv_detections) == 0:
            return detections

        # supervision stores xyxy as float32; class_id and confidence may be None
        xyxy = sv_detections.xyxy  # shape (N, 4)
        class_ids = sv_detections.class_id  # ndarray | None
        confidences = sv_detections.confidence  # ndarray | None
        labels: list[str] | None = (
            list(sv_detections.data.get("class_name", [])) if sv_detections.data else None
        )

        for i in range(len(sv_detections)):
            x1, y1, x2, y2 = (int(v) for v in xyxy[i])
            class_id: int = int(class_ids[i]) if class_ids is not None else 0
            confidence: float = float(confidences[i]) if confidences is not None else 1.0
            class_name: str = labels[i] if labels and i < len(labels) else str(class_id)
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                    bbox=(x1, y1, x2, y2),
                )
            )

        return detections

    async def detect(self, frame: np.ndarray) -> list[Detection]:
        """Async detection — runs inference in thread pool to avoid GIL blocking.

        Args:
            frame: BGR or RGB numpy array (H, W, 3).

        Returns:
            List of Detection objects above the confidence threshold.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.detect_sync, frame)

    def close(self) -> None:
        """Shut down the thread pool executor."""
        self._executor.shutdown(wait=False)
