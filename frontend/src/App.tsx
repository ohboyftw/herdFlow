import './index.css';
import { VideoPanel } from './components/VideoPanel';
import { VoicePanel } from './components/VoicePanel';
import { AlertPanel } from './components/AlertPanel';
import { Dashboard } from './components/Dashboard';

// Static mock data for AlertPanel during development.
// Wire real data from useAlerts / useSceneGraph when LiveKit is connected.
const MOCK_ALERTS = [
  {
    id: 'mock-1',
    type: 'ISOLATION_DETECTED',
    severity: 'warning' as const,
    entity_track_id: 'cow-007',
    description: 'Animal has been isolated from the herd for more than 30 minutes.',
    timestamp: new Date().toISOString(),
  },
  {
    id: 'mock-2',
    type: 'FEED_ABSENCE',
    severity: 'alert' as const,
    entity_track_id: 'cow-012',
    description: 'No feed visit recorded in the last 4 hours.',
    timestamp: new Date(Date.now() - 900_000).toISOString(),
  },
];

export default function App() {
  return (
    <div className="flex h-screen bg-slate-900 text-white overflow-hidden">
      {/* Left: Video feed (70%) */}
      <div className="w-[70%] relative">
        <VideoPanel overlayData={null} />
      </div>

      {/* Right: Control panel (30%) */}
      <div className="w-[30%] flex flex-col border-l border-slate-700 overflow-y-auto">
        <VoicePanel />
        <AlertPanel alerts={MOCK_ALERTS} />
        <Dashboard sceneGraph={null} />
      </div>
    </div>
  );
}
