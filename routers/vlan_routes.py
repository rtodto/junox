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
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }

@router.post("/assign-vlan/{device_id}/{vlan_id}")
def set_access_interface_vlan(
    device_id: int, 
    interface_name: str, 
    vlan_id: int, 
    db: Session = Depends(get_db)
    ):
    """
    Redis job dispatcher to assign an interface to a specific vlan.
    """

    device_ip = apiut.device_id_to_ip(device_id)
    job = q.enqueue(set_interface_vlan_job,device_ip,interface_name,vlan_id) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
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

    job = q.enqueue(set_trunk_interface_vlan_job,device_ip,interface_name,vlan_id) 
    return {
        "job_id": job.get_id(),
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }



@router.get("/{device_id}/fetch-vlans")
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
        "status": "Queued",
        "monitor_url": f"/job/{job.get_id()}"
    }


