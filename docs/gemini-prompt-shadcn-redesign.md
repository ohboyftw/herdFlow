# Gemini Prompt: HerdFlow React Frontend Redesign with shadcn/ui

Copy everything below the line into Gemini.

---

## Task

Redesign the HerdFlow React frontend using **shadcn/ui** components. HerdFlow is a real-time AI veterinary co-pilot that monitors livestock via camera, runs AI detection, and lets a farmer talk to a voice agent about their herd.

## Tech Stack

- React 18 + TypeScript + Vite
- Tailwind CSS 3.x (already configured)
- @livekit/components-react (LiveKit WebRTC — DO NOT replace)
- shadcn/ui (to be added — use `npx shadcn@latest init` then individual components)

## Current Architecture (DO NOT change)

The app connects to a LiveKit room via WebRTC. Data flows through these hooks that subscribe to LiveKit data channels — **keep all hooks unchanged**:

```typescript
// These hooks are the data layer — DO NOT modify
useSceneGraph(room)  → SceneGraph | null    // from 'scene_graph' data channel
useAlerts(room)      → Alert[]              // from 'alerts' data channel
useOverlay(room)     → OverlayData | null   // from 'overlay' data channel
useZones(room)       → DetectedZone[]       // from 'zone_config' data channel
useVoiceAssistant()  → { state: AgentState } // from @livekit/components-react
```

## Data Types (from backend Pydantic models, auto-generated)

```typescript
interface HerdSummary {
  total_visible: number;
  standing: number;
  lying: number;
  walking: number;
  feeding: number;
  drinking: number;
}

interface TrackedEntity {
  track_id: string;
  class_name: string;
  confidence: number;
  bbox: number[];        // [x1, y1, x2, y2] in pixels (1280x720)
  centroid: number[];    // [cx, cy]
  velocity: number[];    // [vx, vy]
  behavior: string;      // 'standing' | 'lying' | 'walking' | 'feeding' | 'drinking'
  behavior_duration_s: number;
  zone: string;
  isolation_score: number;   // 0-1, >0.7 = isolated
  flags: string[];
}

interface Alert {
  id: string;
  type: string;           // e.g. 'isolation', 'prolonged_lying'
  severity: 'info' | 'warning' | 'alert' | 'critical';
  entity_track_id: string;
  description: string;
  timestamp: string;
  resolved: boolean;
}

interface SceneGraph {
  timestamp: string;
  frame_id: number;
  herd_summary: HerdSummary;
  tracked_entities: TrackedEntity[];
  zones: Record<string, { occupancy: number }>;
  active_alerts: Alert[];
}

interface OverlayBox {
  track_id: string;
  bbox: number[];         // [x1, y1, x2, y2]
  behavior: string;
  flags: string[];
}

interface OverlayData {
  frame_id: number;
  boxes: OverlayBox[];
}

interface DetectedZone {
  name: string;
  x1: number; y1: number; x2: number; y2: number;  // normalized 0-1
  confidence: number;
}
```

## Current Layout (to be redesigned)

```
┌──────────────────────────────────┬──────────────────┐
│                                  │   VoicePanel     │
│         VideoPanel               │   (voice UI +    │
│   (video + SVG bounding boxes    │    transcript)   │
│    + zone overlays + legend)     ├──────────────────┤
│                                  │   AlertPanel     │
│         70% width                │   (alert cards)  │
│                                  ├──────────────────┤
│                                  │   Dashboard      │
│                                  │   (herd stats +  │
│                                  │    behaviors +   │
│                                  │    zone bars)    │
└──────────────────────────────────┴──────────────────┘
```

## Design Requirements

### 1. Overall Layout
- Dark theme (slate-900/950 background) — this is used in barns, outdoors, low-light
- Responsive: desktop-first (demo is on desktop) but should not break on tablet
- Video panel should be the hero — largest area, always visible
- Right sidebar for voice, alerts, dashboard — scrollable independently
- Consider a bottom bar for mobile instead of right sidebar

### 2. VideoPanel (most important)
- Full-width video with SVG bounding box overlay (keep existing SVG logic)
- **LIVE badge** top-left with pulsing dot (keep existing)
- **Frame counter** or timestamp somewhere subtle
- Zone overlays from `useZones` hook (keep existing dynamic zone rendering)
- Bounding boxes: green (active), blue (resting), amber (alert flags) — keep existing colors
- Track ID labels above boxes (keep existing)
- **Legend** bottom-right (keep existing but use shadcn Badge components)
- Consider a **mini-map** or entity list overlay showing all tracked animals

### 3. VoicePanel
- Agent status indicator: disconnected / connecting / listening / speaking / thinking
- **Waveform or audio visualizer** when agent is speaking (use CSS animation, no canvas)
- Transcript area showing conversation (currently empty — will be wired later)
- Mic toggle button (mute/unmute)
- Use shadcn `Card`, `Badge`, `Button` components
- Should feel like a modern chat interface (WhatsApp/iMessage style bubbles)

### 4. AlertPanel
- Alert cards with severity color coding (info=blue, warning=amber, alert=orange, critical=red with pulse)
- Dismiss button per alert
- Active alert count badge in header
- Use shadcn `Alert`, `Badge`, `Button` components
- Critical alerts should be visually prominent (border glow, larger)
- Show entity track ID and relative timestamp ("2m ago")

### 5. Dashboard (Herd Summary)
- Total visible animals (large number)
- Active alerts count (highlighted if > 0)
- Behavior breakdown as horizontal bars or donut chart
- Zone occupancy bars
- Use shadcn `Card`, `Progress` components
- **DO NOT show mock data** — show "Awaiting live feed..." when sceneGraph is null
- Remove the MOCK_SCENE constant entirely

### 6. shadcn Components to Use
- `Card`, `CardHeader`, `CardTitle`, `CardContent` — for all panels
- `Badge` — for severity labels, status indicators, track IDs
- `Button` — for mic toggle, dismiss alerts
- `Progress` — for behavior bars, zone occupancy
- `Alert`, `AlertTitle`, `AlertDescription` — for alert cards
- `Separator` — between sections
- `ScrollArea` — for scrollable panels
- `Tooltip` — for bounding box hover info (if feasible)

### 7. Color Palette
Keep the existing color semantics:
- Emerald/green: active, healthy, connected
- Blue: resting, info-level
- Amber: warning, flagged
- Orange: alert
- Red: critical, urgent
- Violet: thinking state
- Sky: listening state
- Slate: backgrounds, borders, muted text

### 8. What NOT to Change
- LiveKit connection logic (`LiveKitRoom`, `RoomAudioRenderer`)
- Data hooks (`useSceneGraph`, `useAlerts`, `useOverlay`, `useZones`)
- SVG bounding box rendering logic in VideoPanel
- The `types/generated.ts` file
- The `main.tsx` entry point

### 9. What to Remove
- `MOCK_SCENE` constant in Dashboard.tsx — show empty state instead
- Any hardcoded mock data
- The hardcoded `ZONE_BOUNDARIES` array (replaced by `useZones` hook, already done)

## Current Component Files (for reference)

### App.tsx
```tsx
import './index.css';
import { LiveKitRoom, RoomAudioRenderer, useRoomContext } from '@livekit/components-react';
import { VideoPanel } from './components/VideoPanel';
import { VoicePanel } from './components/VoicePanel';
import { AlertPanel } from './components/AlertPanel';
import { Dashboard } from './components/Dashboard';
import { useSceneGraph } from './hooks/useSceneGraph';
import { useAlerts } from './hooks/useAlerts';

const LIVEKIT_URL = import.meta.env.VITE_LIVEKIT_URL ?? 'ws://localhost:7880';
const LIVEKIT_TOKEN: string | undefined = import.meta.env.VITE_LIVEKIT_TOKEN;

function RoomContent() {
  const room = useRoomContext();
  const sceneGraph = useSceneGraph(room);
  const alerts = useAlerts(room);

  return (
    <div className="flex h-screen bg-slate-900 text-white overflow-hidden">
      <div className="w-[70%] relative">
        <VideoPanel room={room} />
      </div>
      <div className="w-[30%] flex flex-col border-l border-slate-700 overflow-y-auto">
        <VoicePanel />
        <AlertPanel alerts={alerts} />
        <Dashboard sceneGraph={sceneGraph} />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <LiveKitRoom
      serverUrl={LIVEKIT_URL}
      token={LIVEKIT_TOKEN}
      audio={true}
      video={false}
      style={{ height: '100dvh' }}
    >
      <RoomAudioRenderer />
      <RoomContent />
    </LiveKitRoom>
  );
}
```

## Deliverables

1. Updated `App.tsx` with shadcn layout
2. Updated `VideoPanel.tsx` — keep SVG logic, wrap in shadcn Card
3. Updated `VoicePanel.tsx` — shadcn Card/Badge/Button, chat-style transcript
4. Updated `AlertPanel.tsx` — shadcn Alert/Badge components
5. Updated `Dashboard.tsx` — shadcn Card/Progress, NO mock data
6. Any new shared components (e.g., `StatusBadge.tsx`)
7. Instructions for running `npx shadcn@latest init` and which components to add

## Style Reference

The UI should feel like a **professional monitoring dashboard** — think Bloomberg terminal meets farm management software. Dense information display, dark theme, subtle animations, clear hierarchy. The farmer glances at this while working — information should be scannable in 2 seconds.

Do NOT make it look like a consumer app. It's a professional tool.
