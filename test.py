import asyncio
import websockets
import struct

YDOC_NAME = "test-doc"  # match the document name your server expects
WS_URL = "ws://localhost:4444/collaboration/ws"  # update this to your Yjs websocket URL

# See: https://github.com/yjs/y-websocket#message-types
MESSAGE_SYNC = 0
MESSAGE_AWARENESS = 1

async def connect_to_yjs():
    uri = f"{WS_URL}/{YDOC_NAME}"
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        # Send a basic SYNC message (client-to-server)
        # Format: <messageType><payload>
        # Minimal ping with type 0 (sync) and no payload
        await websocket.send(struct.pack("B", MESSAGE_SYNC))
        print("Sent SYNC message")

        # Wait and print incoming messages
        while True:
            message = await websocket.recv()
            print(f"Received {len(message)} bytes: {message.hex()}")

asyncio.run(connect_to_yjs())
