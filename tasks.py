from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from fastapi import FastAPI,HTTPException, status
import redis

def create_vlan_job(host, vlan_id, vlan_name):
    dev = Device(host=host, user='root', password='lab123')
    try:
        dev.open()
        cu = Config(dev)
        commands = f"""
        set vlans auto-vlan-{vlan_id} vlan-id {vlan_id}
        """
        cu.load(commands,format="set")
        cu.commit(comment=f"Automation: Created VLAN {vlan_id}")
        dev.close()
        
        r = redis.Redis(host='localhost', port=6379)
        message = f"VLAN {vlan_id} has been deployed successfully."
        print(f"DEBUG: Publishing to Redis: {message}")
    
        r.publish("job_notifications", message)
        
        return {
            "status": "success",
            #"device_id": device_id,
            "vlan_id": vlan_id,
            "message": f"VLAN {vlan_id} successfully created."
        }    

    except ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to the device"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    