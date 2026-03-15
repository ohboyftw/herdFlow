import { useEffect, useState } from 'react';
import { Room, RoomEvent } from 'livekit-client';
import type { Alert } from '../types/generated';

export function useAlerts(room: Room | undefined): Alert[] {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (!room) return;

    const handler = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic: string | undefined,
    ) => {
      if (topic === 'alerts') {
        try {
          const alert = JSON.parse(new TextDecoder().decode(payload)) as Alert;
          setAlerts((prev) => {
            const filtered = prev.filter((a) => a.id !== alert.id);
            return [...filtered, alert].slice(-20);
          });
        } catch (e) {
          console.error('Failed to parse alert:', e);
        }
      }
    };

    room.on(RoomEvent.DataReceived, handler);
    return () => {
      room.off(RoomEvent.DataReceived, handler);
    };
  }, [room]);

  return alerts;
}
