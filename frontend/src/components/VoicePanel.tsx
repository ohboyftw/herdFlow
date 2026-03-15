import { useState } from 'react';
import { useVoiceAssistant } from '@livekit/components-react';
import type { AgentState } from '@livekit/components-react';

interface TranscriptEntry {
  id: string;
  speaker: 'user' | 'agent';
  text: string;
  timestamp: string;
}

// Mock transcript for development; replaced by LiveKit audio transcriptions in production
const MOCK_TRANSCRIPT: TranscriptEntry[] = [
  {
    id: '1',
    speaker: 'agent',
    text: 'HerdFlow online. Monitoring 24 cattle across 3 zones.',
    timestamp: '09:00:01',
  },
];

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

function AgentStatusBadge({ state }: { state: AgentState }) {
  if (state === 'disconnected') {
    return (
      <span className="flex items-center gap-1 text-xs text-slate-400">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
        Disconnected
      </span>
    );
  }

  if (state === 'connecting' || state === 'pre-connect-buffering') {
    return (
      <span className="flex items-center gap-1 text-xs text-slate-400">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-pulse" />
        Connecting...
      </span>
    );
  }

  if (state === 'speaking') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-400">
        <SpeakingIndicator />
        <span>Speaking</span>
      </span>
    );
  }

  if (state === 'listening') {
    return (
      <span className="flex items-center gap-1 text-xs text-sky-400">
        <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
        Listening
      </span>
    );
  }

  if (state === 'thinking') {
    return (
      <span className="flex items-center gap-1 text-xs text-violet-400">
        <span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
        Thinking...
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 text-xs text-emerald-400">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
      Ready
    </span>
  );
}

export function VoicePanel() {
  const [micActive, setMicActive] = useState(false);
  const [transcript] = useState<TranscriptEntry[]>(MOCK_TRANSCRIPT);
  const { state: agentState } = useVoiceAssistant();

  const isMicOn = micActive || agentState === 'listening';

  return (
    <div className="flex flex-col border-b border-slate-700 bg-slate-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-200">Voice Assistant</span>
          <AgentStatusBadge state={agentState} />
        </div>

        {/* Microphone status indicator + toggle */}
        <button
          onClick={() => setMicActive((prev) => !prev)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
            isMicOn
              ? 'bg-red-600 hover:bg-red-700 text-white'
              : 'bg-slate-700 hover:bg-slate-600 text-slate-200'
          }`}
          aria-label={isMicOn ? 'Stop microphone' : 'Start microphone'}
        >
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            {isMicOn ? (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5.25 7.5A2.25 2.25 0 017.5 5.25h9a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25h-9a2.25 2.25 0 01-2.25-2.25v-9z"
              />
            ) : (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
              />
            )}
          </svg>
          {isMicOn ? 'Stop' : 'Mic'}
        </button>
      </div>

      {/* Transcript */}
      <div className="flex flex-col gap-2 px-4 pb-3 max-h-48 overflow-y-auto">
        {transcript.map((entry) => (
          <div
            key={entry.id}
            className={`flex flex-col gap-0.5 ${entry.speaker === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs ${
                entry.speaker === 'user'
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
            Press Mic to start talking to HerdFlow
          </p>
        )}
      </div>
    </div>
  );
}
