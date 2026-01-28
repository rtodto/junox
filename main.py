from fastapi import FastAPI, Depends
from juniper_cfg.routers import auth_routes,device_routes,vlan_routes,other_routes,interface_routes
from juniper_cfg.auth import get_current_user

#WebSocket
import asyncio
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
import os
from fastapi.middleware.cors import CORSMiddleware


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
        "database": "connected" # Check DB health later
    }

# WebSocket
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

origins = [
    "http://127.0.0.1:8001",
    "http://localhost:8001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}", decode_responses=True)

@app.websocket("/ws/logs/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    
    # Use the async pubsub
    async with redis_client.pubsub() as pubsub:
        await pubsub.subscribe(f"logs_{job_id}")
        await websocket.send_text("✔ Connected to Redis channel...")
        
        try:
            while True:
                # Use get_message with a timeout to keep the loop responsive
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message:
                    await websocket.send_text(message["data"])
                
                # Check if the websocket is still alive
                await asyncio.sleep(0.01)
        except WebSocketDisconnect:
            print(f"Client disconnected from job {job_id}")
        except Exception as e:
            await websocket.send_text(f"Error: {str(e)}")