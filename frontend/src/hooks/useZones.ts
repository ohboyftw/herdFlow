import { useEffect, useState } from 'react';
import type { Room } from 'livekit-client';

export interface DetectedZone {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
}

export function useZones(room: Room | undefined): DetectedZone[] {
  const [zones, setZones] = useState<DetectedZone[]>([]);

  useEffect(() => {
    if (!room) return;

    const handler = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic: string | undefined,
    ) => {
      if (topic === 'zone_config') {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload)) as DetectedZone[];
          setZones(data);
        } catch (e) {
          console.error('Failed to parse zone_config:', e);
        }
      }
    };

    room.on('dataReceived', handler);
    return () => {
      room.off('dataReceived', handler);
    };
  }, [room]);

  return zones;
}
