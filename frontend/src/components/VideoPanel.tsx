import type { OverlayData } from '../types/generated';

interface VideoPanelProps {
  overlayData?: OverlayData | null;
}

export function VideoPanel({ overlayData: _overlayData }: VideoPanelProps) {
  return (
    <div className="relative w-full h-full bg-slate-950 flex items-center justify-center">
      {/* Video placeholder — LiveKit track will be injected here */}
      <div className="flex flex-col items-center gap-3 text-slate-500">
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

      {/* SVG overlay — bounding boxes from OverlayData will be rendered here */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none"
        viewBox="0 0 1280 720"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Overlay boxes rendered here once LiveKit video is active */}
      </svg>

      {/* Status badge */}
      <div className="absolute top-3 left-3 flex items-center gap-2 bg-slate-900/80 rounded-md px-2 py-1">
        <span className="w-2 h-2 rounded-full bg-slate-500 animate-pulse" />
        <span className="text-xs text-slate-400">STANDBY</span>
      </div>
    </div>
  );
}
