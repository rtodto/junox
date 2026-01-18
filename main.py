from typing import Union
from fastapi import FastAPI,HTTPException, WebSocket, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from redis import asyncio as aioredis # This is the key change!


#Cache implementation
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
from contextlib import asynccontextmanager


import asyncio
#Juniper Modules
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.op.ethport import EthPortTable
from lxml import etree

#redis
from redis import Redis
from rq import Queue
#from tasks import create_vlan_job, fetch_mac_table_job, fetch_vlans_job,provision_device_job  # Import the function reference
from tasks import *

#SQL
from sqlalchemy.orm import Session
from typing import List
import models
from database import get_db 
from schemas import DeviceResponse
import auth, models, database
from fastapi.middleware.cors import CORSMiddleware # Import the middleware

#Custom classes
from utils import Utils 
from apiutils import APIUtils  

from dotenv import load_dotenv
import os
load_dotenv()

#Temp: Until we implement better auth
DEVICE_USER = os.getenv("DEVICE_USER")
DEVICE_PASSWORD=os.getenv("DEVICE_PASSWORD")
REDIS_HOST=os.getenv("REDIS_HOST", "localhost")
REDIS_PORT=os.getenv("REDIS_PORT", "6379")

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_conn = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    # Create ONE async connection pool
    pool = aioredis.ConnectionPool.from_url(
        redis_conn, encoding="utf8", decode_responses=True
    )
    redis_client = aioredis.Redis(connection_pool=pool)
    
    # Init Cache with this client
    FastAPICache.init(RedisBackend(redis_client), prefix="fastapi-cache")
    
    # Store it in app state so other routes can use it
    app.state.redis = redis_client
    
    yield
    
    # Clean up
    await redis_client.close()
    await pool.disconnect()

# For RQ (Sync), it's okay to keep one separate sync connection 
# because RQ doesn't support async redis-py clients yet.
sync_redis = Redis(host='localhost', port=6379)
q = Queue('juniper', connection=sync_redis)


##
app = FastAPI(lifespan=lifespan)
apiut = APIUtils()
ut = Utils()

#TEMP for local testing
# 1. Define the "origins" (the addresses of your frontend)
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# 2. Add the middleware to your app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Allows these specific origins
    allow_credentials=True,           # Allows cookies and headers (like JWT)
    allow_methods=["*"],              # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],              # Allows all headers
)

#Utilities
def device_id_to_IP(device_id: int, db: Session):
    """
    We take device_id as input and we return the IP address of the device 
    """
    device = db.query(models.DeviceNet).filter(models.DeviceNet.id==device_id).first()

    if not device:
        return None
    
    return device.ip_address

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    # 1. Find user
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    # 2. Check password
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # 3. Create Token
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Use the pool from app state
    redis = websocket.app.state.redis 
    pubsub = redis.pubsub()
    await pubsub.subscribe("job_notifications")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # With decode_responses=True in the pool, no need to .decode()
                await websocket.send_text(message["data"]) 
    finally:
        await pubsub.unsubscribe("job_notifications")


@app.get("/devices", response_model=List[DeviceResponse])
def get_devices(db: Session = Depends(get_db),
                token: str = Depends(auth.oauth2_scheme),
                current_user: models.User = Depends(auth.get_current_user)
                ):
    # 1. Query all devices from the database
    devices = db.query(models.DeviceNet).all()
    
    print(f"User {current_user.username} is requesting the device list.")
    
    # restrict access here
    if not current_user.is_active:
         raise HTTPException(status_code=400, detail="Inactive user")

    # 2. Return the list (FastAPI automatically converts these to JSON)
    return devices


@app.get("/device/{device_id}/interfaces")
#@cache(expire=120)
def get_interfaces(device_id: int,db: Session = Depends(get_db)):
    
    device_ip = apiut.device_id_to_ip(device_id)
    dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
    dev.open()
    ports = EthPortTable(dev)
    ports.get()
    dev.close()
    
    return {"ports": ports.items()}

@app.get("/device/switching_interfaces/{device_id}")
def get_switching_interfaces(device_id: int,db: Session = Depends(get_db)):
    
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)

    job = q.enqueue(get_switching_interfaces_job, device_ip) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@app.post("/device/provision/{device_hostname}")
def provision_device(device_hostname: str, db: Session = Depends(get_db)):
    
    #This is not so strict I know but it works for now
    if ut.identify_address_type(device_hostname) == "Hostname":
        device_ip = ut.resolve_hostname(device_hostname)
    else:
        device_ip = device_hostname
    
    job = q.enqueue(provision_device_job, device_ip) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }    



@app.post("/device/create-vlan/{device_id}/{vlan_id}")
def create_vlan(device_id: int, vlan_id: int, vlan_name: str, db: Session = Depends(get_db)):

  device_ip = apiut.device_id_to_ip(device_id)
  job = q.enqueue(create_vlan_job,device_ip,vlan_id,vlan_name) 
  return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@app.post("/device/assign-vlan/{device_id}/{vlan_id}")
def set_interface_vlan(
    device_id: int, 
    interface_name: str, 
    vlan_id: int, 
    db: Session = Depends(get_db)
    ):
    device_ip = apiut.device_id_to_ip(device_id)
    job = q.enqueue(set_interface_vlan_job,device_ip,interface_name,vlan_id) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }
    

@app.get("/device/{device_id}/fetch-vlans")
def fetch_vlans(device_id: int, db: Session = Depends(get_db)):
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    job = q.enqueue(fetch_vlans_job, 
                    device_ip, device_id,
                    on_success=run_post_fetch_vlans_job
                    #on_failure=run_post_fetch_vlans_job
                    ) 
    job.meta["device_id"] = device_id
    job.save_meta()

    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@app.get("/device/{device_id}/mac-table")
def fetch_mac_table(device_id: int, db: Session = Depends(get_db)):
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    job = q.enqueue(fetch_mac_table_job, device_ip, device_id) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@app.get("/job/{job_id}")
def get_job_status(job_id: str):
    job = q.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.is_failed:
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(job.exc_info)
        }
        
    return {
        "job_id": job_id,
        "status": job.get_status(),
        "result": job.result
    }