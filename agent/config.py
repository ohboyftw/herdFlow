"""HerdFlow configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # Google AI
    google_api_key: str = ""

    # RF-DETR
    rfdetr_model: str = "rf-detr-small"
    rfdetr_detection_threshold: float = 0.3
    rfdetr_display_threshold: float = 0.5

    # HerdFlow
    max_fps: float = 2.0
    min_interval_ms: int = 200
    alert_prolonged_lying_s: float = 3600
    alert_isolation_threshold: float = 0.7
    alert_missed_feeding_s: float = 14400
    entity_id_prefix: str = "COW-"
    demo_video_path: str = "demo_videos/cattle_pen_720p.mp4"
    use_real_detector: bool = False
    google_credentials_file: str = "credentials.json"

    # Gemini model selection
    gemini_model: str = "gemini-3-flash-preview"
    enable_analyst_subagent: bool = False  # v2: Gemini 3 sub-agent for deep analysis

    # Zone config (frame-relative percentages)
    zone_config: dict = {
        "feed_area": {"x1": 0.0, "y1": 0.0, "x2": 0.3, "y2": 0.5},
        "water_trough": {"x1": 0.7, "y1": 0.0, "x2": 1.0, "y2": 0.3},
        "rest_area": {"x1": 0.3, "y1": 0.5, "x2": 1.0, "y2": 1.0},
    }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
