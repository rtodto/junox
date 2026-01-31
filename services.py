from redis import Redis
from rq import Queue
from juniper_cfg.utils import Utils
from juniper_cfg.apiutils import APIUtils
from .models import *
from .database import SessionLocal
from sqlalchemy import update

#ncclient imports
from ncclient import manager
#ping imports
import subprocess

# Initialize single instances of your tools
apiut = APIUtils()
ut = Utils()

# RQ Setup
sync_redis = Redis(host='localhost', port=6379)
q = Queue('juniper', connection=sync_redis)


def svc_is_device_exists(device_ip: str):
    """
    Check if device already exists in database
    """
    db = SessionLocal()
    try:
        device = db.query(DeviceNet).filter(DeviceNet.ip_address == device_ip).first()
        return device is not None
    finally:
        db.close()

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
