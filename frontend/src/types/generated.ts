// AUTO-GENERATED from agent/models.py — do not edit manually


export interface HerdSummary {
  total_visible: number;
  standing: number;
  lying: number;
  walking: number;
  feeding: number;
  drinking: number;
}

export interface ZoneOccupancy {
  occupancy: number;
}

export interface TrackedEntity {
  track_id: string;
  class_name: string;
  confidence: number;
  bbox: number[];
  centroid: number[];
  velocity: number[];
  behavior: string;
  behavior_duration_s: number;
  zone: string;
  last_feed_visit_s: number;
  isolation_score: number;
  flags: string[];
}

export interface Alert {
  id?: string;
  type: string;
  severity: Severity;
  entity_track_id: string;
  description: string;
  timestamp?: string;
  resolved?: boolean;
  resolved_at?: string | null;
}

export interface SceneGraph {
  timestamp: string;
  frame_id: number;
  herd_summary: HerdSummary;
  tracked_entities: TrackedEntity[];
  zones: Record<string, ZoneOccupancy>;
  active_alerts: Alert[];
}

export interface OverlayBox {
  track_id: string;
  bbox: number[];
  behavior: string;
  flags: string[];
}

export interface OverlayData {
  frame_id: number;
  boxes: OverlayBox[];
}

export type Severity = 'info' | 'warning' | 'alert' | 'critical';
