import asyncio
import websockets

async def test_y_provider():
    uri = "ws://localhost:4444"
    async with websockets.connect(uri) as websocket:
        print("✅ Connected to Y-provider WebSocket server!")

asyncio.run(test_y_provider())
