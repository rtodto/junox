from juniper_cfg.services import svc_get_device_ip_by_id_async
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

@router.get("/{device_id}/interfaces_job")
async def get_interfaces(
    device_id: int,
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Fetches the list of configured interfaces (Non-blocking dispatcher).
    """
    # 1. Use our async helper to fetch the IP
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 2. Enqueue the worker job
    # We keep the 'on_success' callback logic as is
    job = q.enqueue(
        get_interfaces_job, 
        device_ip, 
        device_id,
        on_success=post_get_interfaces_job
    )
    
    # 3. Handle Metadata
    job.meta["device_id"] = device_id
    job.save_meta()
    
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@router.get("/{device_id}/interfaces_db")
async def get_interfaces_list(
    device_id: int, 
    db: AsyncSession = Depends(get_async_db)
):
    """
    Fetches the list of configured interfaces from the database (Non-blocking).
    """
    # 1. Await the functional async utility
    interfaces = await svc_get_interfaces_list_async(db, device_id)
    
    # 2. Return the data
    # If interfaces is None, it returns {"interfaces": null} 
    # unless you want to raise a 404.
    if interfaces is None:
        return {"interfaces": [], "count": 0}

    return {
        "interfaces": interfaces,
        "count": len(interfaces)
    }

@router.get("/switching_interfaces/{device_id}")
async def get_switching_interfaces(
    device_id: int,
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Redis job to fetch ethernet switching interfaces (Non-blocking).
    """
    
    # 1. Resolve IP using the async utility
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)

    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 2. Enqueue the worker job
    # This remains synchronous as Redis writes are extremely fast
    job = q.enqueue(get_switching_interfaces_job, device_ip, device_id) 
    
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }


