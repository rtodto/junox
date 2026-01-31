from fastapi import APIRouter,HTTPException,Depends,Form,Request
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from juniper_cfg.database import get_async_db,get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import *
from juniper_cfg.services import q,apiut,ut

#redis
from redis import Redis
from rq import Queue
from juniper_cfg.tasks import *

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)

@router.get("/", response_model=List[DeviceResponse])
def get_devices(db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    """
    Returns the list of network devices from database
    """

    # 1. Query all devices from the database
    devices = db.query(models.DeviceNet).all()
    
    print(f"User {current_user.username} is requesting the device list.")
    
    # restrict access here
    if not current_user.is_active:
         raise HTTPException(status_code=400, detail="Inactive user")

    # 2. Return the list (FastAPI automatically converts these to JSON)
    return devices


@router.post("/provision/{device_hostname}", 
             response_model=JobResponse,
             status_code=status.HTTP_202_ACCEPTED 
             #This is a super cool response to my lovely Django. Hey baby, I got your request
             #and working on it, super nice.
)             
def provision_device(device_hostname: str, 
                    payload: DeviceProvisionRequest,
                    request: Request,
                    db: Session = Depends(get_db)
                    ):
    """
    Registers a new device and initiates the background provisioning task.
    Supports an optional session_id for real-time WebSocket logging.
    """
    #This is not so strict I know but it works for now
    if ut.identify_address_type(device_hostname) == "Hostname":
        device_ip = ut.resolve_hostname(device_hostname)
    else:
        device_ip = device_hostname
    
    #this is from JS frontend during device registration
    session_id = getattr(payload, "session_id", None)
    session_channel = f"logs_{session_id}" if session_id else None


    if svc_is_device_exists(device_ip):
        error_msg = f"\x1b[31m--- [FAILED] Device already exists ---\x1b[0m"
        r.expire(session_channel,1800)
        r.publish(session_channel, error_msg)
        raise HTTPException(status_code=400, detail="Device already exists")
    

    job = q.enqueue(provision_device_job, device_ip, payload.username, payload.password,session_id) 
    job_id = job.get_id()
    monitor_url = str(request.url_for("get_job_status", job_id=job_id))
    
    if session_channel:
        start_msg = "--- Worker job initiated ---"
        r.publish(session_channel,start_msg)

    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": monitor_url
    }    

@router.get("/{device_id}/mac-table")
def fetch_mac_table(device_id: int, db: Session = Depends(get_db)):
    """
    Redis dispatcher to fetch mac table
    """
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    job = q.enqueue(fetch_mac_table_job, device_ip, device_id) 
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }


@router.get("/inventory/stats")
async def get_inventory_stats(db: AsyncSession = Depends(get_async_db)):
    """
    Returns counts for charts:
    {
        "platform": {"juniper": 12, "cisco": 4},
        "type": {"router": 10, "switch": 6},
        ...
    }
    """
    # The fields we want to visualize
    columns_map = {
        "platform": DeviceNet.platform,
        "type": DeviceNet.type,
        "os_version": DeviceNet.os_version,
        "model": DeviceNet.model,
        "brand": DeviceNet.brand
    }
    
    stats = {}

    for key, column in columns_map.items():
        # SELECT column, COUNT(column) FROM devices GROUP BY column
        stmt = select(column, func.count(column)).group_by(column)
        result = await db.execute(stmt)
        
        # Convert list of tuples [('juniper', 10), ('cisco', 5)] -> Dict
        # Handle potential None values if columns are nullable
        stats[key] = { (row[0] or "Unknown"): row[1] for row in result.all() }

    return stats   