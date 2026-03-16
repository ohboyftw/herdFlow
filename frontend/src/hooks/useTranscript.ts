import { useEffect, useState } from 'react';
import type { Room } from 'livekit-client';

export interface TranscriptEntry {
  id: string;
  speaker: 'farmer' | 'agent';
  text: string;
  timestamp: string;
  final: boolean;
}

export function useTranscript(room: Room | undefined): TranscriptEntry[] {
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);

  useEffect(() => {
    if (!room) return;

    const handler = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic: string | undefined,
    ) => {
      if (topic === 'transcript') {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload));
          if (data.final && data.text?.trim()) {
            setEntries((prev) => [
              ...prev.slice(-50), // keep last 50 entries
              {
                id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                speaker: data.speaker ?? 'farmer',
                text: data.text,
                timestamp: new Date().toLocaleTimeString(),
                final: true,
              },
            ]);
          }
        } catch {
          // ignore malformed transcript
        }
      }
    };

    room.on('dataReceived', handler);
    return () => {
      room.off('dataReceived', handler);
    };
  }, [room]);

  return entries;
}
