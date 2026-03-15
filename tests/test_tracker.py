"""Tests for ByteTrack tracker wrapper."""

from __future__ import annotations

from agent.perception.tracker import Tracker
from tests.conftest import make_detection


def test_tracker_assigns_persistent_ids():
    tracker = Tracker()
    dets = [make_detection(bbox=(100, 200, 300, 400))]
    tracked = tracker.update(dets, frame_id=1)
    assert len(tracked) == 1
    assert tracked[0].track_id.startswith("COW-")

    # Same position next frame should keep same ID
    tracked2 = tracker.update(dets, frame_id=2)
    assert tracked2[0].track_id == tracked[0].track_id


def test_tracker_new_detection_gets_new_id():
    tracker = Tracker()
    dets1 = [make_detection(bbox=(100, 200, 300, 400))]
    tracker.update(dets1, frame_id=1)

    # ByteTrack may need a couple frames to confirm new detections
    dets2 = [
        make_detection(bbox=(100, 200, 300, 400)),
        make_detection(bbox=(500, 200, 700, 400)),
    ]
    tracker.update(dets2, frame_id=2)
    tracked3 = tracker.update(dets2, frame_id=3)
    assert len(tracked3) == 2
    ids = {t.track_id for t in tracked3}
    assert len(ids) == 2  # two unique IDs
