from fastapi import APIRouter,HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from juniper_cfg.database import get_db
from juniper_cfg import auth, models
from juniper_cfg.schemas import *
from juniper_cfg.services import q,apiut,ut

#redis
#from redis import Redis
#from rq import Queue
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry, DeferredJobRegistry
from juniper_cfg.tasks import *

router = APIRouter(
    prefix="/other",
    tags=["other"]
)

@router.get("/job/{job_id}", response_model=JobStatusResponse, name="get_job_status")
def get_job_status(job_id: str):
    job = q.fetch_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    response_data = {
        "job_id": job_id,
        "status": job.get_status(), # Returns 'queued', 'started', 'finished', or 'failed'
        "result": job.result,
        "error": None
    }
    
    if job.is_failed:
        response_data["status"] = "error"
        response_data["error"] = str(job.exc_info)
        
    return response_data

@router.get("/jobs/all")
def get_all_jobs():
    """
    Aggregates jobs from all RQ registries to provide a complete history.
    """
    all_jobs = []
    
    # 1. Define registries to check
    registries = [
        StartedJobRegistry(queue=q),
        FinishedJobRegistry(queue=q),
        FailedJobRegistry(queue=q),
        DeferredJobRegistry(queue=q)
    ]
    
    # 2. Get Job IDs from registries + the main queue
    job_ids = set(q.job_ids) # Currently queued
    for registry in registries:
        job_ids.update(registry.get_job_ids())
    
    # 3. Fetch details for each job
    for job_id in job_ids:
        job = q.fetch_job(job_id)
        if job:
            # We determine a friendly status
            status = job.get_status()
            if status == "queued":
                display_status = "running" # or "queued"
            elif status == "started":
                display_status = "running"
            elif status == "finished":
                display_status = "completed"
            elif status == "failed":
                display_status = "failed"
            else:
                display_status = status

            all_jobs.append({
                "id": job_id,
                "task_type": job.func_name.split('.')[-1], # e.g., 'provision_device'
                "target": job.args[0] if job.args else "N/A", # Assuming first arg is IP
                "status": display_status,
                "created_at": job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else "N/A",
                "ended_at": job.ended_at.strftime('%Y-%m-%d %H:%M:%S') if job.ended_at else "N/A",
                "result": job.result
            })
            
    # Sort by creation time (newest first)
    all_jobs.sort(key=lambda x: x['created_at'], reverse=True)
    
    return all_jobs