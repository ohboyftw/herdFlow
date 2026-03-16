import { useEffect, useRef } from 'react';
import { useVoiceAssistant } from '@livekit/components-react';
import type { AgentState } from '@livekit/components-react';
import type { Room } from 'livekit-client';
import type { TranscriptEntry } from '../hooks/useTranscript';

interface VoicePanelProps {
  room: Room | undefined;
  transcript: TranscriptEntry[];
}

function SpeakingIndicator() {
  return (
    <span className="flex items-end gap-0.5 h-4" aria-label="Agent speaking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1 rounded-sm bg-emerald-400 animate-bounce"
          style={{
            height: `${8 + i * 3}px`,
            animationDelay: `${i * 0.12}s`,
            animationDuration: '0.6s',
          }}
        />
      ))}
    </span>
  );
}

function ConnectionBadge({ room }: { room: Room | undefined }) {
  if (!room) {
    return (
      <span className="flex items-center gap-1 text-xs text-slate-500">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
        No room
      </span>
    );
  }

  const state = room.state;
  if (state === 'connected') {
    const participants = room.remoteParticipants.size;
    return (
      <span className="flex items-center gap-1 text-xs text-emerald-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        Connected {participants > 0 ? `(${participants + 1})` : ''}
      </span>
    );
  }

  if (state === 'connecting' || state === 'reconnecting') {
    return (
      <span className="flex items-center gap-1 text-xs text-amber-400">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        {state === 'reconnecting' ? 'Reconnecting...' : 'Connecting...'}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 text-xs text-red-400">
      <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
      Disconnected
    </span>
  );
}

function AgentStatusBadge({ state }: { state: AgentState }) {
  const configs: Record<string, { color: string; label: string; pulse?: boolean; indicator?: React.ReactNode }> = {
    disconnected: { color: 'text-slate-400', label: 'Offline' },
    connecting: { color: 'text-slate-400', label: 'Connecting...', pulse: true },
    'pre-connect-buffering': { color: 'text-slate-400', label: 'Buffering...', pulse: true },
    speaking: { color: 'text-emerald-400', label: 'Speaking', indicator: <SpeakingIndicator /> },
    listening: { color: 'text-sky-400', label: 'Listening', pulse: true },
    thinking: { color: 'text-violet-400', label: 'Thinking...', pulse: true },
  };

  const cfg = configs[state] ?? { color: 'text-emerald-400', label: 'Ready' };

  return (
    <span className={`flex items-center gap-1.5 text-xs ${cfg.color}`}>
      {cfg.indicator ?? (
        <span className={`w-1.5 h-1.5 rounded-full bg-current ${cfg.pulse ? 'animate-pulse' : ''}`} />
      )}
      <span>{cfg.label}</span>
    </span>
  );
}

export function VoicePanel({ room, transcript }: VoicePanelProps) {
  const { state: agentState } = useVoiceAssistant();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll transcript to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const isListening = agentState === 'listening';

  return (
    <div className="flex flex-col border-b border-slate-700 bg-slate-900">
      {/* Header with connection + agent status */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-semibold text-slate-200">HerdFlow Voice</span>
          <ConnectionBadge room={room} />
        </div>
        <AgentStatusBadge state={agentState} />
      </div>

      {/* Active listening indicator */}
      {isListening && (
        <div className="mx-4 mb-2 flex items-center gap-2 bg-sky-900/30 border border-sky-700/50 rounded-md px-3 py-1.5">
          <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
          <span className="text-xs text-sky-300">Listening... speak now</span>
          <span className="flex items-end gap-px ml-auto h-3">
            {[0, 1, 2, 3, 4].map((i) => (
              <span
                key={i}
                className="w-0.5 bg-sky-400 rounded-sm animate-pulse"
                style={{
                  height: `${4 + Math.random() * 8}px`,
                  animationDelay: `${i * 0.1}s`,
                  animationDuration: '0.5s',
                }}
              />
            ))}
          </span>
        </div>
      )}

      {/* Transcript */}
      <div ref={scrollRef} className="flex flex-col gap-2 px-4 pb-3 max-h-48 overflow-y-auto">
        {transcript.map((entry) => (
          <div
            key={entry.id}
            className={`flex flex-col gap-0.5 ${entry.speaker === 'farmer' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs ${
                entry.speaker === 'farmer'
                  ? 'bg-blue-700 text-white'
                  : 'bg-slate-700 text-slate-200'
              }`}
            >
              {entry.text}
            </div>
            <span className="text-[10px] text-slate-500">{entry.timestamp}</span>
          </div>
        ))}
        {transcript.length === 0 && (
          <p className="text-xs text-slate-500 text-center py-2">
            {room?.state === 'connected'
              ? 'Speak to HerdFlow — your words will appear here'
              : 'Waiting for connection...'}
          </p>
        )}
      </div>
    </div>
  );
}
