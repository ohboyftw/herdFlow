import { useEffect, useRef } from 'react';
import type { Room } from 'livekit-client';
import { useOverlay } from '../hooks/useOverlay';
import type { OverlayBox } from '../types/generated';

interface VideoPanelProps {
  room: Room | undefined;
}

// Normalized zone boundaries [x1, y1, x2, y2] matching agent/config.py
const ZONE_BOUNDARIES: Array<{ name: string; x1: number; y1: number; x2: number; y2: number }> = [
  { name: 'feed area', x1: 0.0, y1: 0.0, x2: 0.3, y2: 0.5 },
  { name: 'water trough', x1: 0.7, y1: 0.0, x2: 1.0, y2: 0.3 },
  { name: 'rest area', x1: 0.3, y1: 0.5, x2: 1.0, y2: 1.0 },
];

// SVG viewBox dimensions (matches agent video resolution)
const VB_W = 1280;
const VB_H = 720;

function boxColor(box: OverlayBox): string {
  if (box.flags.length > 0) return '#f59e0b'; // amber-400 — has alert flags
  if (box.behavior === 'lying' || box.behavior === 'resting') return '#60a5fa'; // blue-400
  return '#34d399'; // emerald-400 — active
}

export function VideoPanel({ room }: VideoPanelProps) {
  const overlayData = useOverlay(room);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Attach LiveKit remote video track to the video element
  useEffect(() => {
    if (!room || !videoRef.current) return;

    const attachFirstVideoTrack = () => {
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.videoTrackPublications.values()) {
          if (publication.track && videoRef.current) {
            publication.track.attach(videoRef.current);
            return;
          }
        }
      }
    };

    attachFirstVideoTrack();

    const onTrackSubscribed = () => attachFirstVideoTrack();
    room.on('trackSubscribed', onTrackSubscribed);
    return () => {
      room.off('trackSubscribed', onTrackSubscribed);
    };
  }, [room]);

  const hasVideo = !!overlayData || (room && room.remoteParticipants.size > 0);

  return (
    <div className="relative w-full h-full bg-slate-950 flex items-center justify-center">
      {/* LiveKit video element */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="w-full h-full object-contain"
      />

      {/* Placeholder shown when no video stream yet */}
      {!hasVideo && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-500 pointer-events-none">
          <svg
            className="w-16 h-16"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9A2.25 2.25 0 004.5 18.75z"
            />
          </svg>
          <p className="text-sm font-medium">Connecting to LiveKit...</p>
          <p className="text-xs text-slate-600">Awaiting video stream</p>
        </div>
      )}

      {/* SVG overlay — bounding boxes + zone boundaries */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Zone boundary rectangles */}
        {ZONE_BOUNDARIES.map((zone) => (
          <g key={zone.name}>
            <rect
              x={zone.x1 * VB_W}
              y={zone.y1 * VB_H}
              width={(zone.x2 - zone.x1) * VB_W}
              height={(zone.y2 - zone.y1) * VB_H}
              fill="none"
              stroke="rgba(148,163,184,0.25)"
              strokeWidth={2}
              strokeDasharray="8 6"
            />
            <text
              x={zone.x1 * VB_W + 8}
              y={zone.y1 * VB_H + 18}
              fill="rgba(148,163,184,0.55)"
              fontSize={13}
              fontFamily="sans-serif"
              fontWeight="500"
            >
              {zone.name}
            </text>
          </g>
        ))}

        {/* Animal bounding boxes */}
        {overlayData?.boxes.map((box) => {
          const [x1, y1, x2, y2] = box.bbox;
          const bw = x2 - x1;
          const bh = y2 - y1;
          const color = boxColor(box);
          return (
            <g key={box.track_id}>
              <rect
                x={x1}
                y={y1}
                width={bw}
                height={bh}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
                rx={3}
              />
              {/* Track ID label above box */}
              <rect
                x={x1}
                y={y1 - 20}
                width={Math.max(box.track_id.length * 7.5, 48)}
                height={18}
                fill={`${color}33`}
                rx={2}
              />
              <text
                x={x1 + 4}
                y={y1 - 6}
                fill={color}
                fontSize={12}
                fontFamily="monospace"
                fontWeight="600"
              >
                {box.track_id}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Status badge */}
      <div className="absolute top-3 left-3 flex items-center gap-2 bg-slate-900/80 rounded-md px-2 py-1">
        {room ? (
          <>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-emerald-300">LIVE</span>
          </>
        ) : (
          <>
            <span className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
            <span className="text-xs text-slate-400">STANDBY</span>
          </>
        )}
      </div>

      {/* Overlay legend */}
      {overlayData && (
        <div className="absolute bottom-3 right-3 flex flex-col gap-1 bg-slate-900/80 rounded-md px-2.5 py-2">
          <span className="text-[9px] text-slate-400 uppercase tracking-wider mb-0.5">Legend</span>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-emerald-400 rounded" />
            <span className="text-[10px] text-slate-300">Active</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-blue-400 rounded" />
            <span className="text-[10px] text-slate-300">Resting</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 bg-amber-400 rounded" />
            <span className="text-[10px] text-slate-300">Alert flag</span>
          </div>
        </div>
      )}
    </div>
  );
}
