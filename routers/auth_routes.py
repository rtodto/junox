from fastapi import APIRouter, Depends, HTTPException, status,Header
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from juniper_cfg import auth  # Absolute imports from the main directory
from juniper_cfg import models
from juniper_cfg.database import *
from juniper_cfg.services import *
from rq.job import Job
from juniper_cfg.tasks import *

router = APIRouter(tags=["Authentication"])


@router.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: AsyncSessionLocal = Depends(get_async_db) # Using async session
):
    # 1. Find user (Async way)
    stmt = select(models.User).where(models.User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    # 2. Check password
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # 3. Create Token: Sync logic
    access_token = auth.create_access_token(data={"sub": user.username})

    # 4. Create refresh token 
    refresh_token = auth.create_refresh_token(data={"sub": user.username}) 
    
    return {
         "access_token": access_token,
         "refresh_token": refresh_token,
         "token_type": "bearer"
    }


@router.post("/refresh")
async def refresh_token(refresh_token: str = Body(..., embed=True)):    
    try:
        # 1. Decode and verify the refresh token
        # This is usually a CPU-bound task (JWT decoding)
        payload = auth.verify_refresh_token(refresh_token)
        
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
            
    except Exception: 
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")

    # 2. Issue a new access token
    # Again, creation is typically sync math/hashing
    new_access_token = auth.create_access_token(data={"sub": username})
    
    return {
        "access_token": new_access_token, 
        "token_type": "bearer"
    }

# In production, move this to an environment variable (.env)
EDA_API_KEY = "lab123"

async def verify_eda_token(x_api_key: str = Header(...)):
    """
    Dependency that checks if the request has the correct API Key.
    """
    if x_api_key != EDA_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return x_api_key

@router.post("/webhooks/eda-dispatch", dependencies=[Depends(verify_eda_token)])
async def eda_dispatcher(payload: dict):
    # This code only runs if verify_eda_token succeeds
    log_detail = payload.get("log_detail")
    device_ip = payload.get("device_ip")
    task_type = payload.get("task_type")
    db = AsyncSessionLocal()
    device_id = await svc_get_device_id_by_hostname_async(db, device_ip)
    
    if device_id is None:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if task_type == "sync_request":
        job = Job.create(func=sync_device_config_job, args=(device_id,), connection=system_q.connection)
        system_q.enqueue_job(job)
        
    
    print("--------ANSIBLE WEBHOOKS HEADERS---------")
    print(f"log_detail: {log_detail}")
    print(f"device_ip: {device_ip}")
    print(f"task_type: {task_type}")
    
    # ... your existing dispatcher logic ...
    return {"status": "success"}

@router.get("/ping")
async def ping(current_user: models.User = Depends(auth.get_current_user)):
    # If get_current_user is async, FastAPI awaits it before entering here.
    return {"message": "pong"}
    