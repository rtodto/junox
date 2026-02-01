from fastapi import APIRouter,HTTPException,Depends,Form,Request
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from juniper_cfg.database import get_async_db,get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import *
from juniper_cfg.services import *

#redis
from redis import Redis
from rq import Queue
from rq.job import Job
from juniper_cfg.tasks import *

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)

@router.get("/", response_model=List[DeviceResponse])
async def get_devices(
    db: AsyncSession = Depends(get_async_db), # Use the async session
    current_user: models.User = Depends(auth.get_current_user)
):
    """
    Returns the list of network devices from database (Non-blocking)
    """
    # 1. Security check first (Best practice to check before heavy DB hits)
    if not current_user.is_active:
         raise HTTPException(status_code=400, detail="Inactive user")

    # 2. Use the modern select statement
    stmt = select(models.DeviceNet)
    
    # 3. AWAIT the execution
    result = await db.execute(stmt)
    
    # 4. Extract the objects from the result
    # .scalars().all() turns the rows into a list of DeviceNet objects
    devices = result.scalars().all()
    
    print(f"User {current_user.username} is requesting the device list.")

    return devices


@router.post("/provision/{device_hostname}", 
             response_model=JobResponse,
             status_code=status.HTTP_202_ACCEPTED 
             #This is a super cool response to my lovely Django. Hey baby, I got your request
             #and working on it, super nice.
)             
async def provision_device(device_hostname: str, 
                    payload: DeviceProvisionRequest,
                    request: Request,
                    db: AsyncSession = Depends(get_async_db)
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

    #DB check so use await and async func.
    if await svc_is_device_exists_async(device_ip):
        error_msg = f"\x1b[31m--- [FAILED] Device already exists ---\x1b[0m"
        r.expire(session_channel,1800)
        r.publish(session_channel, error_msg)
        raise HTTPException(status_code=400, detail="Device already exists")
    

    job = Job.create(
        provision_device_job, 
        args=(device_ip,payload.username,payload.password,session_id),
        connection=system_q.connection,
    )
    
    job.meta["run_chain"] = True #By this we inform other jobs in the chain that req is from endpoint. 
    job.save_meta()
    system_q.enqueue_job(job)
    job_id = job.get_id()

    monitor_url = str(request.url_for("get_job_status", job_id=job_id))
    
    if session_channel:
        start_msg = "---Provisioning job initiated ---"
        r.publish(session_channel,start_msg)

    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": monitor_url
    }    


@router.get("/{device_id}/mac-table")
async def fetch_mac_table(
    device_id: int, 
    db: AsyncSession = Depends(get_async_db)
):
    # Call the new async helper
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
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
    # 1. Total Device Count (The 'Hero' Number)
    total_stmt = select(func.count(DeviceNet.id))
    total_res = await db.execute(total_stmt)
    total_devices = total_res.scalar() or 0

    # 2. Sync Status Breakdown (Operational vs Failed)
    status_stmt = select(DeviceNet.sync_status, func.count(DeviceNet.id)).group_by(DeviceNet.sync_status)
    status_res = await db.execute(status_stmt)
    status_map = {row[0]: row[1] for row in status_res.all()}

    # Initialize response with new summary keys
    response_data = {
        "total_devices": total_devices,
        "operational_count": status_map.get("synced", 0),
        "failed_count": status_map.get("failed", 0),
        "pending_count": status_map.get("pending", 0),
        "global": {}, 
        "os_by_vendor": {}
    }

    # --- Existing Logic Below ---
    global_map = {
        "type": DeviceNet.type,
        "model": DeviceNet.model,
        "vendor": DeviceNet.vendor
    }
    
    # Fetch Global Stats
    for key, column in global_map.items():
        stmt = select(column, func.count(column)).group_by(column)
        result = await db.execute(stmt)
        response_data["global"][key] = { (row[0] or "Unknown"): row[1] for row in result.all() }

    # OS Versions Grouped by Vendor
    stmt_os = select(
        DeviceNet.vendor, 
        DeviceNet.os_version, 
        func.count(DeviceNet.id)
    ).group_by(DeviceNet.vendor, DeviceNet.os_version)
    
    result_os = await db.execute(stmt_os)
    
    for vendor, os_ver, count in result_os.all():
        vendor_key = vendor or "Unknown"
        os_key = os_ver or "Unknown"
        if vendor_key not in response_data["os_by_vendor"]:
            response_data["os_by_vendor"][vendor_key] = {}
        response_data["os_by_vendor"][vendor_key][os_key] = count

    return response_data