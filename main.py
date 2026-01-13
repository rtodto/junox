from typing import Union
from fastapi import FastAPI,HTTPException, status, WebSocket, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from redis import asyncio as aioredis # This is the key change!
import asyncio
#Juniper Modules
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.op.ethport import EthPortTable
from lxml import etree

#redis
from redis import Redis
from rq import Queue
from tasks import create_vlan_job  # Import the function reference

#SQL
from sqlalchemy.orm import Session
from typing import List
import models
from database import get_db # The function we wrote earlier
from schemas import DeviceResponse
import auth, models, database
from fastapi.middleware.cors import CORSMiddleware # Import the middleware


redis_conn = Redis(host='localhost', port=6379)
# We name the queue 'juniper' to keep it organized
q = Queue('juniper', connection=redis_conn,default_result_ttl=86400)


app = FastAPI()
dev = Device(host='192.168.120.10', user='root', password='lab123')
host='192.168.120.10'

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
    
    # Use the modern redis-py async client
    redis = await aioredis.from_url("redis://localhost:6379")
    pubsub = redis.pubsub()
    await pubsub.subscribe("job_notifications")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"].decode("utf-8"))
    except Exception as e:
        print(f"Connection closed: {e}")
    finally:
        await redis.close() # Clean up connection


@app.get("/devices", response_model=List[DeviceResponse])
def get_devices(db: Session = Depends(get_db),
                token: str = Depends(auth.oauth2_scheme),
                current_user: models.User = Depends(auth.get_current_user)
                ):
    # 1. Query all devices from the database
    devices = db.query(models.Device).all()
    
    print(f"User {current_user.username} is requesting the device list.")
    
    # restrict access here
    if not current_user.is_active:
         raise HTTPException(status_code=400, detail="Inactive user")

    # 2. Return the list (FastAPI automatically converts these to JSON)
    return devices


@app.get("/device/{device_id}/interfaces")
async def get_interfaces(device_id: int):

    dev.open()
    ports = EthPortTable(dev)
    ports.get()
    dev.close()
    
    return {"ports": ports.items()}

@app.post("/device/{device_id}/{vlan_id}")
def set_vlan(vlan_id: int,vlan_name: str):

  job = q.enqueue(create_vlan_job,host,vlan_id,vlan_name) 
  return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }
    
@app.get("/device/{device_id}/mac-table")
def get_mac_table(device_id: int):

    try:

        dev.open()
        results=[]
        mac_data = dev.rpc.get_ethernet_switching_table_information()
        #raw_xml = etree.tostring(mac_data, encoding='unicode', pretty_print=True)
        #print(raw_xml)
        # 2. Parse the XML into a Python List of Dictionaries
        results = []
        # vJunos typically uses 'l2ng' tags for Next-Gen Layer 2
        for entry in mac_data.xpath('.//l2ng-mac-entry'):
            results.append({
                "vlan": entry.findtext('l2ng-l2-mac-vlan-name', default="N/A").strip(),
                "mac": entry.findtext('l2ng-l2-mac-address', default="N/A").strip(),
                "interface": entry.findtext('l2ng-l2-mac-logical-interface', default="N/A").strip(),
            })
            
        dev.close()

        return {
            "status": "success",
            "device_id": device_id,
            "mac_table" : results
        }
    
    except ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to the device"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )