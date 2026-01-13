from pydantic import BaseModel

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

    class Config:
        from_attributes = True # Allows Pydantic to read SQLAlchemy objects