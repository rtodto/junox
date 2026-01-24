from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Body
from sqlalchemy.orm import Session
from juniper_cfg import auth, database  # Absolute imports from the main directory
from juniper_cfg import models
router = APIRouter(tags=["Authentication"])


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    # 1. Find user
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    # 2. Check password
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    # 3. Create Token
    access_token = auth.create_access_token(data={"sub": user.username})

    # 4. Create refresh token 
    refresh_token = auth.create_refresh_token(data={"sub": user.username}) 
    
    return {
         "access_token": access_token,
         "refresh_token": refresh_token,
         "token_type": "bearer"}


@router.post("/refresh")
def refresh_token(refresh_token: str = Body(..., embed=True)):    
    try:
        # 1. Decode and verify the refresh token
        # You should have a function in auth.py that uses your SECRET_KEY
        payload = auth.verify_refresh_token(refresh_token)
        
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
            
    except Exception: # Handle ExpiredSignatureError or JWTError
        raise HTTPException(status_code=401, detail="Refresh token expired or invalid")

    # 2. Issue a new access token
    new_access_token = auth.create_access_token(data={"sub": username})
    
    return {
        "access_token": new_access_token, 
        "token_type": "bearer"
    }