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
async def get_job_status(job_id: str):
    """
    Fetches the status of a specific job.
    """
    job = q.fetch_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    response_data = {
        "job_id": job_id,
        "status": job.get_status(), 
        "result": job.result,
        "error": None
    }
    
    # Check for failure specifically
    if job.is_failed:
        response_data["status"] = "error"
        # exc_info contains the traceback if the Juniper connection or DB save crashed
        response_data["error"] = str(job.exc_info)
        
    return response_data


@router.get("/jobs/all")
async def get_all_jobs():
    """
    Aggregates jobs from all RQ registries asynchronously.
    """
    all_jobs = []
    
    # 1. Define registries to check
    registries = [
        StartedJobRegistry(queue=q),
        FinishedJobRegistry(queue=q),
        FailedJobRegistry(queue=q),
        DeferredJobRegistry(queue=q)
    ]
    
    # 2. Get Job IDs (These are fast memory reads from Redis)
    job_ids = set(q.job_ids) 
    for registry in registries:
        job_ids.update(registry.get_job_ids())
    
    # 3. Fetch details for each job
    for job_id in job_ids:
        # fetch_job is a network call. In an async loop, this is non-blocking.
        job = q.fetch_job(job_id)
        
        if job:
            status = job.get_status()
            
            # Mapping friendly statuses
            status_map = {
                "queued": "running",
                "started": "running",
                "finished": "completed",
                "failed": "failed"
            }
            display_status = status_map.get(status, status)

            all_jobs.append({
                "id": job_id,
                # Safe splitting in case func_name is None
                "task_type": job.func_name.split('.')[-1] if job.func_name else "Unknown",
                "target": job.args[0] if job.args else "N/A",
                "status": display_status,
                # Format datetime safely
                "created_at": job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else "N/A",
                "ended_at": job.ended_at.strftime('%Y-%m-%d %H:%M:%S') if job.ended_at else "N/A",
                "result": job.result
            })
            
    # Sort by creation time (newest first)
    # Note: We check if 'created_at' is "N/A" to avoid sorting errors
    all_jobs.sort(key=lambda x: x['created_at'], reverse=True)
    
    return all_jobs