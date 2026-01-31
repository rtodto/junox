from pydantic import BaseModel, Field, ConfigDict
from typing import Optional,Any

# This defines the JSON structure for the API response
class DeviceResponse(BaseModel):
    id: int
    hostname: str
    ip_address: str
    platform: str
    type: str
    os_version: str
    model: str
    brand: str
    serialnumber: str

    class Config:
        from_attributes = True # Allows Pydantic to read SQLAlchemy objects

class DeviceProvisionRequest(BaseModel):
    # Field allows you to add extra validation or descriptions
    username: str = Field(..., example="admin")
    password: str = Field(..., example="Juniper123")
    session_id: Optional[str] = None # I use this for websocket connection

class JobResponse(BaseModel):
    job_id: str
    status: str
    monitor_url: str

    class Config:
        from_attributes = True

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


class VlanCatalogBase(BaseModel):
    vlan_id: int = Field(..., ge=1, le=4094)
    name: str
    category: str
    description: Optional[str] = None

class VlanCatalogSchema(VlanCatalogBase):
    id: int # The primary key from Postgres

    # This tells Pydantic to convert SQLAlchemy objects to JSON automatically
    model_config = ConfigDict(from_attributes=True)

# CREATE schema It inherits everything from Base
class VlanCreate(VlanCatalogBase):
    pass


