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
    prefix="/interfaces",
    tags=["Interfaces"]
)

@router.get("/{device_id}/interfaces")
#@cache(expire=120)
def get_interfaces(device_id: int,db: Session = Depends(get_db)):
    """
    Fetches the list of configured interfaces from the network device. It dispatches 
    a redis job as it is an I/O job. 
    #show interfaces
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
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.get("/switching_interfaces/{device_id}")
def get_switching_interfaces(device_id: int,db: Session = Depends(get_db)):
    """
    Redis job to fetch ethernet switching interfaces. We grab trunk,access interfaces etc.
    #show ethernet-switching interface
    """
    
    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)

    job = q.enqueue(get_switching_interfaces_job,device_id,device_ip) 
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }


