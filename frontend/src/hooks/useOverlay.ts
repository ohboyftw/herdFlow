import { useEffect, useState } from 'react';
import { Room, RoomEvent } from 'livekit-client';
import type { OverlayData } from '../types/generated';

export function useOverlay(room: Room | undefined): OverlayData | null {
  const [overlayData, setOverlayData] = useState<OverlayData | null>(null);

  useEffect(() => {
    if (!room) return;

    const handler = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic: string | undefined,
    ) => {
      if (topic === 'overlay') {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload)) as OverlayData;
          setOverlayData(data);
        } catch (e) {
          console.error('Failed to parse overlay data:', e);
        }
      }
    };

    room.on(RoomEvent.DataReceived, handler);
    return () => {
      room.off(RoomEvent.DataReceived, handler);
    };
  }, [room]);

  return overlayData;
}
