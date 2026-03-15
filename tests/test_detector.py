"""Tests for RF-DETR detector wrapper and mock detector."""

from __future__ import annotations

import numpy as np

from agent.models import Detection
from agent.perception.detector import MockDetector


def test_mock_detector_returns_detections():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    assert isinstance(detections, list)
    assert all(isinstance(d, Detection) for d in detections)
    assert len(detections) > 0


def test_mock_detector_confidence_above_threshold():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    assert all(d.confidence >= 0.3 for d in detections)


def test_mock_detector_bbox_format():
    detector = MockDetector()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    detections = detector.detect_sync(frame)
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        assert x2 > x1 and y2 > y1
