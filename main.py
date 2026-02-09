from fastapi import FastAPI, Depends
from juniper_cfg.routers import auth_routes,device_routes,vlan_routes,other_routes,interface_routes
from juniper_cfg.auth import get_current_user

#WebSocket
import asyncio
import redis.asyncio as aioredis
from fastapi import WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
import os

#Prometeus Grafana
from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from prometheus_client import Gauge
from juniper_cfg.database import engine  # Import your pooled engine


# WebSocket
load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}", decode_responses=True)

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

# 1. Define your metrics
# Counter: Only goes up (Total jobs)
JOBS_PROCESSED = Counter('eda_jobs_total', 'Total number of EDA jobs processed', ['job_type', 'status'])
# Histogram: Tracks how long things take
JOB_LATENCY = Histogram('eda_job_duration_seconds', 'Time spent processing job', ['job_type'])
# 1. Define Gauges (Gauges can go up AND down, perfect for pools)
DB_POOL_SIZE = Gauge('db_pool_checkedin_connections', 'Connections currently in the pool')
DB_POOL_CHECKEDOUT = Gauge('db_pool_checkedout_connections', 'Connections currently being used')

# 2. The Metrics Endpoint for Prometheus to "Scrape"
@app.get("/metrics")
def metrics():


    # 2. Update Gauge values with live data from the SQLAlchemy engine
    # .size() is the total pool, .checkedin() are idle, .checkedout() are busy
    pool_stats = engine.pool.status()
    
    # Extract numbers from the status string (SQLAlchemy specific)
    # Usually: "Pool size: 10  Connections in pool: 5 Current Overflow: 0"
    DB_POOL_SIZE.set(engine.pool.checkedin())
    DB_POOL_CHECKEDOUT.set(engine.pool.checkedout())

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)




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