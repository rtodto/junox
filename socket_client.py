import asyncio
import websockets
import time

async def listen_with_reconnect():
    uri = "ws://localhost:8000/ws/notifications"
    retry_delay = 1  # Start with 1 second

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print("✅ Connected to Juniper Manager")
                retry_delay = 1  # Reset delay on successful connection
                
                while True:
                    message = await websocket.recv()
                    print(f"🔔 Notification: {message}")

        except (websockets.ConnectionClosed, OSError):
            print(f"❌ Connection lost. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            # Double the delay for next time (up to 60s)
            retry_delay = min(retry_delay * 2, 60)
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            await asyncio.sleep(5)

asyncio.run(listen_with_reconnect())
