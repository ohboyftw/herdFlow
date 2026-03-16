import './index.css';
import { LiveKitRoom, RoomAudioRenderer, useRoomContext } from '@livekit/components-react';
import { VideoPanel } from './components/VideoPanel';
import { VoicePanel } from './components/VoicePanel';
import { AlertPanel } from './components/AlertPanel';
import { Dashboard } from './components/Dashboard';
import { useSceneGraph } from './hooks/useSceneGraph';
import { useAlerts } from './hooks/useAlerts';
import { useTranscript } from './hooks/useTranscript';

const LIVEKIT_URL = import.meta.env.VITE_LIVEKIT_URL ?? 'ws://localhost:7880';
const LIVEKIT_TOKEN: string | undefined = import.meta.env.VITE_LIVEKIT_TOKEN;

function RoomContent() {
  const room = useRoomContext();
  const sceneGraph = useSceneGraph(room);
  const alerts = useAlerts(room);
  const transcript = useTranscript(room);

  return (
    <div className="flex h-screen bg-slate-900 text-white overflow-hidden">
      {/* Left: Video feed (70%) */}
      <div className="w-[70%] relative">
        <VideoPanel room={room} />
      </div>

      {/* Right: Control panel (30%) */}
      <div className="w-[30%] flex flex-col border-l border-slate-700 overflow-y-auto">
        <VoicePanel room={room} transcript={transcript} />
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
