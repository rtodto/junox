from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

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
