from sqlalchemy.sql._elements_constructors import null
from fastapi import APIRouter,HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from juniper_cfg.database import get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import DeviceResponse
from juniper_cfg.services import q,apiut,ut
from juniper_cfg.dbutils import *
from juniper_cfg.schemas import *

#redis
from redis import Redis
from rq import Queue
from juniper_cfg.tasks import *

router = APIRouter(
    prefix="/vlans",
    tags=["vlans"]
)


@router.post("/create-vlan/{device_id}/{vlan_id}")
def create_vlan(device_id: int, vlan_id: int, vlan_name: str, db: Session = Depends(get_db)):
  """
  Redis job dispatches to create vlan on the device.
  """

  device_ip = apiut.device_id_to_ip(device_id)
  job = q.enqueue(create_vlan_job,device_ip,vlan_id,vlan_name) 
  return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }




@router.get("/check_vlan/{device_id}/{vlan_id}")
def check_vlan(device_id: int, vlan_id: int):
    """
    Checks existence of a vlan: check is done against the database
    """
    result = apiut.is_vlan_exist(device_id,vlan_id)

    if result == None:
       return { 
           "status": "success",
           "data" : {
              "vlan_id" : vlan_id,
              "text": "VLAN exists"
           }
           
           }
    else:
        return { 
           "status": "success",
           "result": result
           }


@router.post("/access_vlan/{device_id}/{vlan_id}")
def set_access_interface_vlan(
    device_id: int, 
    interface_name: str, 
    vlan_id: int, 
    db: Session = Depends(get_db)
    ):
    """
    Redis job dispatcher to assign an interface to a specific vlan.
    """


    #Check if vlan exists if not return error don't create it
    result = apiut.is_vlan_exist(device_id,vlan_id)
    if result == None:
        return {
            "status": "error",
            "data": {
               "vlan_id": vlan_id,
               "text": "VLAN does not exist"
            }
        }

    device_ip = apiut.device_id_to_ip(device_id)
    job = q.enqueue(set_interface_vlan_job,device_ip,interface_name,vlan_id) 
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.post("/trunk_vlan/{device_id}/{vlan_id}")
def set_trunk_interface_vlan(device_id: int, interface_name: str, vlan_id: int):
    """
    We set interface_mode to either trunk or access however
    Junos doesn't allow to set an interface to trunk mode without a vlan specified
    so we have to give the code a vlan so user has to give a vlan first. Further 
    operations can just use the set interface vlan endpoint.
    """
    
    device_ip = apiut.device_id_to_ip(device_id)

    #Check if vlan exists if not return error don't create it
    result = apiut.is_vlan_exist(device_id,vlan_id)
    if result == None:
        return {
            "status": "error",
            "data": {
               "vlan_id": vlan_id,
               "text": "VLAN does not exist"
            }
        }

    job = q.enqueue(set_trunk_interface_vlan_job,device_ip,interface_name,vlan_id) 
    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@router.get("/{device_id}/fetch_vlans_job")
def fetch_vlans(device_id: int, db: Session = Depends(get_db)):
    """
    Redis dispatcher: 
          - fetch_vlans_job: fetch vlans from the live device
          - post_fetch_vlans_job: compare them with the existing vlans on the database and add new ones.
    """

    # Calculate IP here (sync)
    device_ip = apiut.device_id_to_ip(device_id)
    if not device_ip:
         raise HTTPException(status_code=404, detail="Device not found")

    job = q.enqueue(fetch_vlans_job, 
                    device_ip, device_id,
                    on_success=post_fetch_vlans_job
                    #on_failure=run_post_fetch_vlans_job
                    ) 
    job.meta["device_id"] = device_id
    job.save_meta()

    return {
        "job_id": job.get_id(),
        "status": "queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.get("/{device_id}/fetch_vlans_db")
def fetch_vlans_db(device_id: int, db: Session = Depends(get_db)):
    """
    Fetches vlans from the database.
    """
    vlans = apiut.get_device_vlans(device_id)
    if not vlans:
        raise HTTPException(status_code=404, detail="Vlans not found")
    return vlans
    
@router.get("/get_vlan_catalog_db", response_model=List[VlanCatalogSchema])    
def get_vlan_catalog_db(db: Session = Depends(get_db)):
    """
    Returns the full global pool of VLANs from the catalog.
    """

    catalog_vlans = db_get_all_vlan_catalog(db)

    if not catalog_vlans:
        raise HTTPException(status_code=404, detail="Vlans not found")
    return catalog_vlans

@router.post("/create_vlan_catalog", response_model=VlanCatalogSchema)
def create_vlan_catalog(vlan_data: VlanCreate, db: Session = Depends(get_db)):
    """
    Creates a new VLAN in the catalog.
    """
    # 1. Check if VLAN ID already exists
    existing = db.query(models.VlanCatalog).filter(models.VlanCatalog.vlan_id == vlan_data.vlan_id).first()
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"VLAN {vlan_data.vlan_id} already exists in the catalog."
        )

    # 2. Create the VLAN (The "Action")
    return db_create_catalog_vlan(db,vlan_data)