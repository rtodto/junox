from fastapi import FastAPI, Depends
from juniper_cfg.routers import auth_routes,device_routes,vlan_routes,other_routes,interface_routes
from juniper_cfg.auth import get_current_user

#WebSocket
import asyncio
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
import os



app = FastAPI(
    title="JunoX API",
    version="0.1.0",
    description="API for Network devices")

# 1. Public routes: No AUTH
app.include_router(auth_routes.router, prefix="/api/v1")

# 2. Protected routes: AUTH
app.include_router(
    device_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    interface_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    vlan_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    other_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

# main.py

@app.get("/health", include_in_schema=False)
def health_check():
    """
    Public health check endpoint
    """

    return {
        "status": "online",
        "version": app.version,
        "database": "connected" # Check DB health later, monitoring etc.
    }

# WebSocket
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")


redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}", decode_responses=True)

@app.websocket("/ws/logs/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    key = f"logs_{session_id}"
    
    try:
        # 1. Immediate acknowledgement
        await websocket.send_text("--- 📡 Established link to background worker ---")

        # 2. Listen to Redis PubSub
        async with redis_client.pubsub() as pubsub:
            await pubsub.subscribe(key)
            
            while True:
                # Listen for messages from the Worker
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message:
                    data = message["data"]
                    # Handle both byte and string data safely
                    decoded_data = data.decode('utf-8') if isinstance(data, bytes) else data
                    await websocket.send_text(decoded_data)
                
                # Keep the connection alive and loop responsive
                await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print(f"User closed session {session_id}")
    except Exception as e:
        print(f"WebSocket Error: {e}")