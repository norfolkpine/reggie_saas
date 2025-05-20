"use client";

import { ReactNode, useMemo } from "react";

import { useSearchParams } from "next/navigation";



export function Room({ children }: { children: ReactNode }) {
  const roomId = useExampleRoomId(
    "demo-doc-1"
  );

  return <>{children}</>;
}

/**
 * This function is used when deploying an example on liveblocks.io.
 * You can ignore it completely if you run the example locally.
 */
function useExampleRoomId(roomId: string) {
  const params = useSearchParams();
  const exampleId = params?.get("exampleId");

  const exampleRoomId = useMemo(() => {
    return exampleId ? `${roomId}-${exampleId}` : roomId;
  }, [roomId, exampleId]);

  return exampleRoomId;
}
