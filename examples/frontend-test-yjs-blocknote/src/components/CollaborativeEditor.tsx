"use client";

import * as Y from "yjs";
import { HocuspocusProvider } from "@hocuspocus/provider";
import React, { useMemo, useState, useEffect } from "react";
import BlockNote, { EditorProps } from "./BlockNote";

// Collaborative text editor with simple rich text, live cursors, and live avatars
function CollaborativeEditor() {
  // Set up Yjs doc and provider (Hocuspocus)
  const doc = useMemo(() => new Y.Doc(), []);
  const roomName = "b1e29c7c-8a1f-4f1a-9b2b-2b1e29c7c8a1";
  const provider = useMemo(() => new HocuspocusProvider({
    url: `ws://localhost:4444/collaboration/ws/?room=${roomName}`,
    name: roomName,
    document: doc,
    // parameters: {
    //   // Send a fake cookie header for local dev bypass
    //   cookie: "dev-session=1"
    // },
    // Add authentication/cookies here if needed
  }), [doc]);

  // WebSocket connection status indicator
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  useEffect(() => {
    function handleStatus(event: { status: string }) {
      setConnectionStatus(event.status);
    }
    provider.on('status', handleStatus);
    return () => {
      provider.off('status', handleStatus);
    };
  }, [provider]);

  let statusColor = '#e53935', statusText = 'Disconnected';
  if (connectionStatus === 'connected') {
    statusColor = '#43a047'; statusText = 'Connected';
  } else if (connectionStatus === 'connecting') {
    statusColor = '#fb8c00'; statusText = 'Connecting';
  } else if (typeof connectionStatus === 'string' && connectionStatus.length > 0) {
    statusColor = '#757575'; statusText = connectionStatus;
  }

  console.log("connectionStatus", connectionStatus, "statusText", statusText);

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1rem', fontWeight: 'bold', fontSize: '1.2rem' }}>
        <span>
          Room: <span style={{ fontFamily: 'monospace', fontSize: '1.1rem' }}>b1e29c7c-8a1f-4f1a-9b2b-2b1e29c7c8a1</span>
          <span style={{
            marginLeft: 12,
            padding: '2px 10px',
            borderRadius: 8,
            background: '#f5f5f5',
            border: `1px solid ${statusColor}`,
            color: statusColor,
            fontWeight: 700,
            fontSize: '1.1rem',
            display: 'inline-flex',
            alignItems: 'center',
          }}>
            ● {statusText}
          </span>
        </span>
      </div>
      <BlockNote doc={doc} provider={provider} roomName="b1e29c7c-8a1f-4f1a-9b2b-2b1e29c7c8a1" />
    </>
  );
}

export default CollaborativeEditor;
