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
    prefix="/other",
    tags=["other"]
)


@router.get("/job/{job_id}")
def get_job_status(job_id: str):
    job = q.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.is_failed:
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(job.exc_info)
        }
        
    return {
        "job_id": job_id,
        "status": job.get_status(),
        "result": job.result
    }