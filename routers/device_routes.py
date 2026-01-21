from fastapi import APIRouter,HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from juniper_cfg.database import get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import DeviceResponse
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
                #current_user: models.User = Depends(auth.get_current_user)
                ):
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


@router.post("/provision/{device_hostname}")
def provision_device(device_hostname: str, db: Session = Depends(get_db)):
    """
    We register a new device on the database and collect the facts from the device.
    """
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
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }