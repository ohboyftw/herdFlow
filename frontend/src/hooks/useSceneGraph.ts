import { useEffect, useState } from 'react';
import { Room, RoomEvent } from 'livekit-client';
import type { SceneGraph } from '../types/generated';

export function useSceneGraph(room: Room | undefined): SceneGraph | null {
  const [sceneGraph, setSceneGraph] = useState<SceneGraph | null>(null);

  useEffect(() => {
    if (!room) return;

    const handler = (
      payload: Uint8Array,
      _participant: unknown,
      _kind: unknown,
      topic: string | undefined,
    ) => {
      if (topic === 'scene_graph') {
        try {
          const data = JSON.parse(new TextDecoder().decode(payload)) as SceneGraph;
          setSceneGraph(data);
        } catch (e) {
          console.error('Failed to parse scene_graph:', e);
        }
      }
    };

    room.on(RoomEvent.DataReceived, handler);
    return () => {
      room.off(RoomEvent.DataReceived, handler);
    };
  }, [room]);

  return sceneGraph;
}
