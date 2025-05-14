import asyncio
import json
import struct
import uuid

import aiohttp
import websockets

# Configuration matching the test environment
PORT = 6666  # matches portWS in hocusPocusWS.test.ts
ROOM_ID = "86c90044-a552-4cc2-beed-02dcd769160d"  # str(uuid.uuid4())  # must be a valid UUID v4 as per tests
WS_URL = f"ws://localhost:{PORT}"
API_URL = "http://localhost:8000"  # matches COLLABORATION_BACKEND_BASE_URL from tests

# Message types from y-websocket
MESSAGE_SYNC = 0
MESSAGE_AWARENESS = 1


async def get_auth_token():
    """Get auth token from the test configuration"""
    return "test-secret-api-key"  # matches COLLABORATION_SERVER_SECRET from tests


async def fetch_document_permissions(room_id, auth_token):
    """Fetch document permissions from backend"""
    headers = {
        "Authorization": auth_token,  # Changed to match test configuration
        "Content-Type": "application/json",
        "Origin": "http://localhost:3000",  # Added origin header as required by tests
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_URL}/api/v1/documents/{room_id}", headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    print(f"Failed to fetch document permissions: {response.status}")
                    print(f"Response text: {await response.text()}")
                    return None
        except Exception as e:
            print(f"Error fetching document permissions: {e}")
            return None


async def connect_to_yjs():
    auth_token = await get_auth_token()

    # First check document permissions
    doc_permissions = await fetch_document_permissions(ROOM_ID, auth_token)
    if not doc_permissions:
        print("Failed to get document permissions")
        return

    if not doc_permissions.get("abilities", {}).get("retrieve", False):
        print("No permission to retrieve this document")
        return

    uri = f"{WS_URL}/?room={ROOM_ID}"

    # Headers matching test requirements
    headers = {
        "Origin": "http://localhost:3000",
        "Authorization": auth_token,  # Changed to match test configuration
        "x-user-id": "test-user-id",  # From hocusPocusWS.test.ts
    }

    try:
        async with websockets.connect(uri, extra_headers=headers) as websocket:
            print(f"Connected to {uri}")
            print(f"Using room ID: {ROOM_ID}")
            print(f"Document permissions: {doc_permissions}")

            # Send awareness update to identify client
            awareness_data = {
                "clientId": str(uuid.uuid4()),
                "user": {"name": "Test User", "id": "test-user-id", "color": "#ff0000"},
            }

            # Send a basic SYNC message (client-to-server)
            await websocket.send(struct.pack("B", MESSAGE_SYNC))
            print("Sent SYNC message")

            # Send awareness update
            awareness_message = struct.pack("B", MESSAGE_AWARENESS) + json.dumps(awareness_data).encode()
            await websocket.send(awareness_message)
            print("Sent awareness message")

            while True:
                try:
                    message = await websocket.recv()
                    msg_type = message[0] if message else None

                    if msg_type == MESSAGE_SYNC:
                        print(f"Received SYNC message: {len(message)} bytes")
                    elif msg_type == MESSAGE_AWARENESS:
                        print(f"Received AWARENESS message: {len(message)} bytes")
                        try:
                            awareness_data = json.loads(message[1:])
                            print(f"Awareness data: {awareness_data}")
                        except:
                            print("Could not parse awareness data")
                    else:
                        print(f"Received unknown message type {msg_type}: {message[1:].hex()}")

                except websockets.exceptions.ConnectionClosedOK:
                    print("Server closed connection normally")
                    break
                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"Connection closed with error: {e}")
                    break
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    asyncio.run(connect_to_yjs())
