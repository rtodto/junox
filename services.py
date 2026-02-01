from redis import Redis
from rq import Queue
from juniper_cfg.utils import Utils
from juniper_cfg.apiutils import APIUtils
from .models import *
from juniper_cfg.database import SessionLocal,AsyncSessionLocal
from sqlalchemy import select,update

#ncclient imports
from ncclient import manager
#ping imports
import subprocess

# Initialize single instances of your tools
apiut = APIUtils()
ut = Utils()

# RQ Setup
sync_redis = Redis(host='localhost', port=6379)
q = Queue('generic', connection=sync_redis)
system_q = Queue('system', connection=sync_redis)
user_q = Queue('user', connection=sync_redis)


async def svc_get_device_vlans_async(db: AsyncSessionLocal, device_id: int):
    """
    Takes device_id as input and returns the list of VLANs asynchronously.
    """
    # 1. Build the select statement
    stmt = select(VLANs).where(VLANs.device_id == device_id)
    
    # 2. Execute and await the result
    result = await db.execute(stmt)
    
    # 3. Use .scalars().all() to get a list of VLAN objects
    vlans = result.scalars().all()

    # 4. Handle the "not found" case
    if not vlans:
        return None
        
    return vlans


async def svc_is_vlan_exist_async(db: AsyncSessionLocal, device_id: int, vlan_id: int):
    """
    Checks if a specific VLAN exists for a device asynchronously.
    """
    # 1. Build the select statement for the specific row
    stmt = select(VLANs.vlan_id).where(
        VLANs.device_id == device_id,
        VLANs.vlan_id == vlan_id
    )
    
    # 2. Execute and await the result
    result = await db.execute(stmt)
    
    # 3. Use scalar_one_or_none to get the single value or None
    return result.scalar_one_or_none()

async def svc_get_interfaces_list_async(db: AsyncSessionLocal, device_id: int):
    """
    Takes device_id as input and returns the list of interfaces asynchronously.
    """
    # 1. Build the select statement
    stmt = select(EthInterfaces).where(EthInterfaces.device_id == device_id)
    
    # 2. Execute and await the result
    result = await db.execute(stmt)
    
    # 3. Extract all objects using .scalars().all()
    interfaces = result.scalars().all()

    # 4. Check if we found anything
    if not interfaces:
        return None
        
    return interfaces

async def svc_get_device_ip_by_id_async(db: AsyncSessionLocal, device_id: int):
    """
    Takes device_id as input and returns the IP address of the device asynchronously.
    """
    # 1. Create the selection statement
    stmt = select(DeviceNet.ip_address).where(DeviceNet.id == device_id)
    
    # 2. Execute the query and await the result
    result = await db.execute(stmt)
    
    # 3. Use scalar_one_or_none to get just the IP address or None
    device_ip = result.scalar_one_or_none()
    
    return device_ip


async def svc_is_device_exists_async(device_ip: str):
    """
    Check if device already exists in database (Async Version)
    """
    # Use the async context manager to handle the session
    async with AsyncSessionLocal() as db:
        try:
            # 1. Prepare the query using the modern 'select' syntax
            stmt = select(DeviceNet).filter(DeviceNet.ip_address == device_ip)
            
            # 2. AWAIT the execution of the query
            result = await db.execute(stmt)
            
            # 3. Use scalar_one_or_none to get the object
            device = result.scalar_one_or_none()
            
            return device is not None
        except Exception as e:
            # Note: with 'async with', the session closes automatically
            raise e

def svc_check_netconf_connectivity(device_ip: str, username: str, password: str):
    """
    Check netconf connectivity to a device
    """
    try:
        # We use lookup='quit' to just test the connection/auth
        with manager.connect(host=device_ip, 
                             port=830, 
                             username=username, 
                             password=password, 
                             hostkey_verify=False) as m:
            print(f"NETCONF session established")
            return True
    except Exception as e:
        print(f"NETCONF connection failed: {e}")
        return False

def svc_ping(device_ip: str):
    """
    Ping a device
    """
    command = ['ping', '-c', '1', device_ip]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        print(f"Ping successful to {device_ip}")
        return True
    else:
        print(f"Ping failed to {device_ip}")
        return False
