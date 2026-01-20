from fastapi import APIRouter,HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from juniper_cfg.database import get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import DeviceResponse
from juniper_cfg.services import q,apiut,ut
#from juniper_cfg.apiutils import *
#from juniper_cfg.utils import *

#redis
from redis import Redis
from rq import Queue
from juniper_cfg.tasks import *

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)

# apiut = APIUtils()
# ut = Utils()

# # For RQ (Sync), it's okay to keep one separate sync connection 
# # because RQ doesn't support async redis-py clients yet.
# sync_redis = Redis(host='localhost', port=6379)
# q = Queue('juniper', connection=sync_redis)


@router.get("/", response_model=List[DeviceResponse])
def get_devices(db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)
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


@router.get("/{device_id}/interfaces")
#@cache(expire=120)
def get_interfaces(device_id: int,db: Session = Depends(get_db)):
    """
    Fetches the list of interfaces from the network device. It dispatches 
    a redis job as it is an I/O job. 
    """
    device_ip = apiut.device_id_to_ip(device_id) 
    job = q.enqueue(get_interfaces_job, 
                   device_ip, device_id,
                   on_success=post_get_interfaces_job
                   )
    job.meta["device_id"] = device_id
    job.save_meta()
    
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.get("/switching_interfaces/{device_id}")
def get_switching_interfaces(device_id: int,db: Session = Depends(get_db)):
    """
    Redis job to fetch ethernet switching interfaces. We grab trunk,access interfaces etc.
    """
    
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)

    job = q.enqueue(get_switching_interfaces_job, device_ip) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

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