from fastapi import FastAPI, Depends
from juniper_cfg.routers import device_routes,auth_routes,vlan_routes,other_routes
from juniper_cfg.auth import get_current_user

app = FastAPI()

# 1. Public routes: No AUTH
app.include_router(auth_routes.router)

# 2. Protected routes: AUTH
app.include_router(
    device_routes.router,
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    vlan_routes.router,
    dependencies=[Depends(get_current_user)]
)

app.include_router(
    other_routes.router,
    dependencies=[Depends(get_current_user)]
)
