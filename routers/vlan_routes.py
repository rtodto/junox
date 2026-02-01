from juniper_cfg.services import *
from sqlalchemy.sql._elements_constructors import null
from fastapi import APIRouter,HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from juniper_cfg.database import *
from juniper_cfg import auth, models
from juniper_cfg.dbutils import *
from juniper_cfg.schemas import *
from juniper_cfg.tasks import *
#redis
from redis import Redis
from rq import Queue


router = APIRouter(
    prefix="/vlans",
    tags=["vlans"]
)


@router.post("/create-vlan/{device_id}/{vlan_id}")
async def create_vlan(
    device_id: int, 
    vlan_id: int, 
    vlan_name: str, 
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Dispatches a Redis job to create a VLAN on the device (Non-blocking).
    """

    # 1. Resolve IP using our functional async utility
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 2. Enqueue the configuration job
    job = q.enqueue(
        create_vlan_job, 
        device_ip, 
        vlan_id, 
        vlan_name
    ) 
    
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }




@router.get("/check_vlan/{device_id}/{vlan_id}")
async def check_vlan(
    device_id: int, 
    vlan_id: int, 
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Checks existence of a vlan against the database (Non-blocking).
    """
    # 1. Await the async helper we built
    result = await svc_is_vlan_exist_async(db, device_id, vlan_id)

    # 2. Logic Check
    # If result is None, the VLAN does NOT exist in our DB
    if result is None:
        return { 
            "status": "not_found",
            "data": {
                "vlan_id": vlan_id,
                "text": "VLAN does not exist in database"
            }
        }
    
    # If result has a value, it exists
    return { 
        "status": "success",
        "result": result,
        "text": "VLAN exists"
    }


@router.post("/access_vlan/{device_id}/{vlan_id}")
async def set_access_interface_vlan(
    device_id: int, 
    interface_name: str, 
    vlan_id: int, 
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Redis job dispatcher to assign an interface to a specific vlan (Non-blocking).
    """

    # 1. Check if VLAN exists using async helper
    vlan_check = await svc_is_vlan_exist_async(db, device_id, vlan_id)
    
    if vlan_check is None:
        raise HTTPException(
            status_code=404, 
            detail={
                "status": "error",
                "vlan_id": vlan_id,
                "text": "VLAN does not exist in database. Please create it first."
            }
        )

    # 2. Resolve Device IP using async helper
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 3. Enqueue the worker job
    job = q.enqueue(
        set_interface_vlan_job, 
        device_ip, 
        interface_name, 
        vlan_id
    ) 
    
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.post("/trunk_vlan/{device_id}/{vlan_id}")
async def set_trunk_interface_vlan(
    device_id: int, 
    interface_name: str, 
    vlan_id: int,
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    We set interface_mode to either trunk or access however
    Junos doesn't allow to set an interface to trunk mode without a vlan specified
    so we have to give the code a vlan so user has to give a vlan first. Further 
    operations can just use the set interface vlan endpoint.
    """
    
    # 1. Check if vlan exists asynchronously
    # We do this first to avoid unnecessary IP lookups if the VLAN is missing
    vlan_check = await svc_is_vlan_exist_async(db, device_id, vlan_id)
    
    if vlan_check is None:
        raise HTTPException(
            status_code=404, 
            detail={
                "status": "error",
                "vlan_id": vlan_id,
                "text": "VLAN does not exist in database"
            }
        )

    # 2. Resolve Device IP using our async helper
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 3. Enqueue the Trunk Configuration job
    job = q.enqueue(
        set_trunk_interface_vlan_job, 
        device_ip, 
        interface_name, 
        vlan_id
    ) 

    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@router.get("/{device_id}/fetch_vlans_job")
async def fetch_vlans(
    device_id: int, 
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Redis dispatcher: 
          - fetch_vlans_job: fetch vlans from the live device
          - post_fetch_vlans_job: compare them with the existing vlans on the database and add new ones.
    """

    # 1. Resolve IP using our functional async utility
    device_ip = await svc_get_device_ip_by_id_async(db, device_id)
    
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    # 2. Enqueue the worker job
    # We include the 'on_success' callback which the RQ worker will 
    # execute after the live device fetch is complete.
    job = q.enqueue(
        fetch_vlans_job, 
        device_ip, 
        device_id,
        on_success=post_fetch_vlans_job
    ) 
    
    # 3. Handle Metadata (Synchronous Redis write)
    job.meta["device_id"] = device_id
    job.save_meta()

    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }


@router.get("/{device_id}/fetch_vlans_db")
async def fetch_vlans_db(
    device_id: int, 
    db: AsyncSessionLocal = Depends(get_async_db)
):
    """
    Fetches vlans from the database (Non-blocking).
    """
    # 1. Await the new functional async utility
    vlans = await svc_get_device_vlans_async(db, device_id)
    
    # 2. Check for existence
    if not vlans:
        raise HTTPException(status_code=404, detail="Vlans not found")
        
    return vlans
    

@router.get("/get_vlan_catalog_db", response_model=List[VlanCatalogSchema])    
async def get_vlan_catalog_db(db: AsyncSessionLocal = Depends(get_async_db)):
    """
    Returns the full global pool of VLANs from the catalog (Non-blocking).
    """

    # 1. Await the async version of your 'get all' utility
    catalog_vlans = await db_get_all_vlan_catalog_async(db)

    # 2. Check for content
    if not catalog_vlans:
        raise HTTPException(status_code=404, detail="Vlan catalog is empty")
        
    return catalog_vlans

@router.post("/create_vlan_catalog", response_model=VlanCatalogSchema)
async def create_vlan_catalog(
    vlan_data: VlanCreate, 
    db: AsyncSessionLocal = Depends(get_async_db) # Using async session
):
    """
    Creates a new VLAN in the catalog (Non-blocking).
    """
    # 1. Check if VLAN ID already exists (Async way)
    stmt = select(models.VlanCatalog).where(models.VlanCatalog.vlan_id == vlan_data.vlan_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"VLAN {vlan_data.vlan_id} already exists in the catalog."
        )

    # 2. Create the VLAN (Awaiting our new async utility)
    return await db_create_catalog_vlan_async(db, vlan_data)