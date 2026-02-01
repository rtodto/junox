from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from juniper_cfg import auth  # Absolute imports from the main directory
from juniper_cfg import models
from juniper_cfg.database import *

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

@router.get("/ping")
async def ping(current_user: models.User = Depends(auth.get_current_user)):
    # If get_current_user is async, FastAPI awaits it before entering here.
    return {"message": "pong"}
    