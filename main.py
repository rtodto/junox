from fastapi import FastAPI, Depends
from juniper_cfg.routers import auth_routes,device_routes,vlan_routes,other_routes,interface_routes
from juniper_cfg.auth import get_current_user

app = FastAPI(
    title="JunoX API",
    version="0.1.0",
    description="API for Network devices")

# 1. Public routes: No AUTH
app.include_router(auth_routes.router, prefix="/api/v1")

# 2. Protected routes: AUTH
app.include_router(
    device_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    interface_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    vlan_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

app.include_router(
    other_routes.router,
    dependencies=[Depends(get_current_user)],
    prefix="/api/v1"
)

# main.py

@app.get("/health", include_in_schema=False)
def health_check():
    """
    Public health check endpoint
    """

    return {
        "status": "online",
        "version": app.version,
        "database": "connected" # Check DB health later
    }