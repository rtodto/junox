from juniper_cfg.services import svc_update_db_interface_tagness
from jnpr.junos.exception import RpcError
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from fastapi import FastAPI,HTTPException, status
import redis
from rq import get_current_job
from rq.job import Job
import json
from juniper_cfg import apiutils
import logging
from juniper_cfg import models 
from dotenv import load_dotenv
import os
#Juniper Modules
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.op.ethport import EthPortTable
from lxml import etree

#An ugly import
from sqlalchemy.dialects.postgresql import insert
from juniper_cfg.database import *
from juniper_cfg.services import *


load_dotenv()

#Temp: Until we implement better auth
DEVICE_USER = os.getenv("DEVICE_USER")
DEVICE_PASSWORD=os.getenv("DEVICE_PASSWORD")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

apiut = apiutils.APIUtils()

LOG_LEVEL = os.getenv("LOG_LEVEL")
logging.basicConfig(level=LOG_LEVEL,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RedisJobs")

def log_to_ws(session_id, ws_message):
    """
    Publishes a message to the WebSocket for a specific session.
    """
    channel = f"logs_{session_id}"
    r.publish(channel, ws_message)

def get_interfaces_job(device_id: int):
    """
    Fetch interface list from the live device. This is show interface output.
    We are interested in the interfaces that are up and running, mac address, description, admin status, oper status.
    However this doesn't include the L3 interfaces.
    """

    device_ip = svc_get_device_ip_by_id_sync(device_id)
    current_job = get_current_job()
    session_id = current_job.meta.get("session_id")
    run_chain = current_job.meta.get("run_chain")
    
    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()
        ports = EthPortTable(dev)
        ports.get()
        dev.close()
        results = ports.items()
        
        if results and current_job and run_chain:
          new_job = Job.create(
            func=post_get_interfaces_job,
            args=(device_id,results,),
            connection=current_job.connection,
          )
          new_job.meta = {
              "session_id": session_id,
              "run_chain": run_chain
          }
          new_job.save_meta()
          new_job.save()
          system_q.enqueue_job(new_job)
            
        return {"interface_list": results}
    

    except Exception as e:
        return {
             "status": "Error",
             "device_ip": device_ip,
             "error": str(e)
        }

def post_get_interfaces_job(device_id,results):
    """
    Synchronizes interfaces to DB after a successful fetch
    """
    current_job = get_current_job()
    interface_raw_data = results
    session_id = current_job.meta.get("session_id")
    run_chain = current_job.meta.get("run_chain")



    if not interface_raw_data:
        return "No interfaces found to sync" 

    data_to_upsert = []
    for interface in interface_raw_data:
        # interface[0] is the name, interface[1] is the dict of attributes
        iface_name = interface[0]
        iface_details = dict(interface[1])
        
        data_to_upsert.append({
            "device_id": device_id,
            "interface_name": iface_name,
            "oper_status": iface_details.get('oper'),
            "admin_status": iface_details.get('admin'),
            "description": iface_details.get('description'),
            "mac_address": iface_details.get('macaddr')
        })

    # Move the DB session OUTSIDE the loop for efficiency
    with SessionLocal() as session:
        try:
            stmt = insert(models.EthInterfaces).values(data_to_upsert)

            # PostgreSQL UPSERT logic
            upsert_stmt = stmt.on_conflict_do_update(
                constraint="uq_device_interface",
                set_={
                    "oper_status": stmt.excluded.oper_status,
                    "admin_status": stmt.excluded.admin_status,
                    "description": stmt.excluded.description,
                    "mac_address": stmt.excluded.mac_address,
                }
            )

            session.execute(upsert_stmt)
            session.commit()

            if run_chain and session_id:
                
                log_to_ws(session_id, "Step 5: Interfaces synced to DB ---")
                #Now time to collect VLAN information from the device
                new_job = Job.create(
                    func=fetch_vlans_job,
                    args=(device_id,),
                    connection=current_job.connection,
                )
                new_job.meta = {
                    "session_id": session_id,
                    "run_chain": run_chain
                }
                new_job.save_meta()
                new_job.save()
                system_q.enqueue_job(new_job)
                

        except Exception as e:
            session.rollback()
            log_to_ws(session_id, f"DATABASE ERROR during sync: {e}")
            raise
      
    

def get_switching_interfaces_job(device_ip: str, device_id:int):
    """
    Fetch switching interfaces from the live device. This is not show interface output.
    """

    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()

        try:
            ##Junos 25.4R1.12(virtual EX)
            all_interfaces = dev.rpc.get_ethernet_switching_interface_details()
            interfaces_result = []
            for entry in all_interfaces.xpath('.//l2ng-l2ald-iff-interface-entry'):
                interface_name = entry.findtext('l2iff-interface-name', default="N/A").strip()
                interface_tagness = entry.findtext('l2iff-interface-vlan-member-tagness', default="N/A").strip()
                if interface_name:
                    interfaces_result.append({
                    "interface_name": interface_name.removesuffix(".0"),
                    "interface_tagness": interface_tagness
                    
                })     
        
        except RpcError as e:
            #Junos 12.3R6.6
            all_interfaces = dev.rpc.get_ethernet_switching_interface_information()
            interfaces_result = []
            for entry in all_interfaces.xpath('.//interface'):
                interface_name = entry.findtext('interface-name', default="N/A").strip()
                vlan_members = entry.xpath('.//interface-vlan-member')
                for member in vlan_members:
                    tagness = member.findtext('interface-vlan-member-tagness')
                    break #we only need once we don't fetch vlans here.
                interface_tagness = tagness

                if interface_name:
                    interfaces_result.append({
                    "interface_name": interface_name.removesuffix(".0"),
                    "interface_tagness": interface_tagness
                    
                })    

        dev.close()
        #Update interface tagness in the database blindly. It is not costing much.
        svc_update_db_interface_tagness(db, device_id,interfaces_result)
        
        return {"interfaces": interfaces_result}
    except Exception as e:
        return {
             "status": "Error",
             "device_ip": device_ip,
             "error": str(e)
        }

    finally:
        if dev:
            dev.close()

def fetch_mac_table_job(device_ip: str, device_id: int):
    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()
        
        mac_data = dev.rpc.get_ethernet_switching_table_information()
        
        logger.info(f"Fetched MAC table for device {device_ip}")
        # Parse the XML into a Python List of Dictionaries
        results = []
        # vJunos typically uses 'l2ng' tags for Next-Gen Layer 2
        for entry in mac_data.xpath('.//l2ng-mac-entry'):
            results.append({
                "vlan": entry.findtext('l2ng-l2-mac-vlan-name', default="N/A").strip(),
                "mac": entry.findtext('l2ng-l2-mac-address', default="N/A").strip(),
                "interface": entry.findtext('l2ng-l2-mac-logical-interface', default="N/A").strip(),
            })
            
        dev.close()
        
        r.publish("job_notifications", "fetch_mac_table")
        return {
            "status": "Success",
            "device_id": device_id,
            "mac_table" : results
        }
    
    except Exception as e:
        return {
             "status": "Error",
             "device_id": device_id,
             "error": str(e)
        }

    finally:
        if dev:
            dev.close()


def provision_device_job(device_ip: str, username: str, password: str, session_id=None):
    """
    This function provisions a device by fetching its facts and returns device_id.
    device_id is used in the chain to call other jobs.
    """

    # 1. Get the Job ID automatically from RQ
    job = get_current_job()
    run_chain = job.meta.get("run_chain", False)
    job_id = job.id if job else "internal"
    session_id = job.meta.get("session_id")
    # Check device connectivity
    log_to_ws(session_id, f"--- Checking ICMP Connectivity ---")
    
    if not svc_ping(device_ip):
        log_to_ws(session_id, f"\x1b[31m---[FAILED] Not responding to ICMP ---\x1b[0m")
        return {
            "status": "Error",
            "device_ip": device_ip,
            "error": "Device is not reachable by ICMP"
        }
    else:
        log_to_ws(session_id, f"\x1b[32m--- ICMP [OK] ---\x1b[0m")

    
    # Check device netconf connectivity
    log_to_ws(session_id, f"--- Checking Netconf Connectivity ---")
    
    if not svc_check_netconf_connectivity(device_ip, username, password):
        log_to_ws(session_id, f"\x1b[31m--- [FAILED] NETCONF ---\x1b[0m")
        return {
            "status": "Error",
            "device_ip": device_ip,
            "error": "Device is not reachable by NETCONF"
        }
    else:
        log_to_ws(session_id, f"\x1b[32m--- NETCONF [OK] ---\x1b[0m")

    try:
        # Use Juniper Device class (imported as Device)
        log_to_ws(session_id, "Step 1: Establishing SSH connection...")
        dev = Device(host=device_ip, user=username, password=password)
        dev.open()
     
        # Use our DB Model class (DeviceNet)
        new_device = models.DeviceNet(
            hostname=dev.facts['hostname'],
            ip_address=device_ip,
            platform="NA",
            type="switch",           
            os_version=dev.facts['version'], 
            model=dev.facts['model'],           
            vendor="NA",
            serialnumber=dev.facts['serialnumber'] # Note: fixed typo from serial_number to serialnumber based on models.py
        )
        logger.info(f"Provisioned device {device_ip}")
        
        dev.close()
        log_to_ws(session_id, "Step 2: Connection Successful.")
        #Dispatch the job to util function
        try:
            db_result = apiut.add_device_to_db(new_device)
            device_id = db_result.id
            if db_result:
                log_to_ws(session_id, "Step 3: Device added to database.")
                if run_chain: #because we can call this function from endpoint or from another job
                    log_to_ws(session_id, "Step 4: Device interfaces are being fetched, please wait...")
                    
                    new_job = Job.create(
                        func=get_interfaces_job,
                        args=(int(device_id),),
                        connection=system_q.connection
                    )
                    new_job.meta["run_chain"] = True
                    new_job.meta["session_id"] = session_id
                    new_job.save_meta()

                    system_q.enqueue_job(new_job)
            else:
                log_to_ws(session_id, "Step 3: Device not added to database.")
        except Exception as e:
            log_to_ws(session_id, f"\x1b[31m[ERROR] {str(e)}\x1b[0m")
            raise e
        
        #log_to_ws(session_id, "\x1b[32m[COMPLETED] Provisioning completed successfully.\x1b[0m")
        return device_id

    except Exception as e:
        return {
             "status": "Error",
             "device_ip": device_ip,
             "error": str(e)
        }

    finally:
        if dev:
            dev.close()

def fetch_vlans_job(device_id: int):
    """
    RQ TASK: Fetches the list of configured vlans from the device.
    """
    device_ip = svc_get_device_ip_by_id_sync(device_id)
    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()
        
        vlans_data = dev.rpc.get_vlan_information()

        
        # Parse the XML into a Python List of Dictionaries
        results = []
        for entry in vlans_data.xpath('.//l2ng-l2ald-vlan-instance-group'):
            results.append({
                "vlan_id": entry.findtext('l2ng-l2rtb-vlan-tag', default="N/A").strip(),
                "vlan_name": entry.findtext('l2ng-l2rtb-vlan-name', default="N/A").strip(),
            })
        logger.info(f"Fetched VLANs for device {device_ip}")
            
        dev.close()

        #redis job id that is created for this task
        current_job = get_current_job()
        job_id = current_job.id 
        message = {
            "job_type": "fetch_vlans",
            "job_id": job_id,
            "device_id": device_id
        }

        session_id = current_job.meta.get("session_id")
        run_chain = current_job.meta.get("run_chain")   
        if results:
            ws_message = f"Step 6: VLANs fetched successfully from the device"
            log_to_ws(session_id, ws_message) 
            #now time to sync the vlans to DB
            new_job = Job.create(
                func=post_fetch_vlans_job,
                args=(device_id,results,),
                connection=current_job.connection,
            )
            new_job.meta = {
                "session_id": session_id,
                "run_chain": run_chain
            }
            new_job.save_meta()
            new_job.save()
            system_q.enqueue_job(new_job)

        else:
            ws_message = f"Step 6: VLANs fetching FAILED."
            log_to_ws(session_id, ws_message)
            return {
                "status": "Error",
                "device_id": device_id,
                "error": "VLANs fetching FAILED."
            }

        return {
            "status": "Success",
            "device_id": device_id,
            "job_type" : "fetch_vlans",
            "vlans" : results
        }
    
    except Exception as e:
        logger.error(f"Error fetching VLANs for device {device_ip}: {str(e)}")
        return {
             "status": "Error",
             "device_id": device_id,
             "error": str(e)
        }



def post_fetch_vlans_job(device_id,results):
    """
    This function is called after the fetch_vlans_job is completed.
    It processes the results of the fetch_vlans_job and updates the database. 
    We ignore (don't compare) the vlan names for simplicity for now. It can be added later.
    Although DB should be the source of truth, we don't delete any vlan from the device if it is not in the DB.
    We only add vlans to the device if they are not in the device. We can add a manual force-sync or diff 
    calculator to give more control to the user.
    """
    device_ip = svc_get_device_ip_by_id_sync(device_id)

    logger.info("!!!!!POST RUN AFTER FETCH VLANS JOB!!!!!")
    #[{'vlan_id': '100', 'vlan_name': 'auto-vlan'}, {'vlan_id': '1000', 'vlan_name': 'auto-vlan-1000'}
    #we get this from the fetch_vlans_job: vlan id is string so we convert it to int
    live_vlan_list = results
    live_vlan_map = {int(vlan['vlan_id']): vlan.get('vlan_name', 'auto-vlan-{}'.format(vlan['vlan_id'])) for vlan in live_vlan_list}
    
    #Get all vlans from DB. Result is a list of dictionaries.
    db_vlan_list = apiut.get_device_vlans(device_id) 
    if db_vlan_list is None: #If there are no vlans in DB, this must be first run.
        db_vlan_list = []
        db_vlan_map = {} #so no vlan mapping i.e vlan_id: vlan_name
    else:
        db_vlan_map = {vlan.vlan_id: vlan.vlan_name for vlan in db_vlan_list}


    #compare live and db vlans: juniper returns vlan_id as string it is a problem
    live_vlan_ids = { int(vlan_id) for vlan_id in live_vlan_map.keys()}
    db_vlan_ids = { int(vlan_id) for vlan_id in db_vlan_map.keys()}
    vlan_id_diff = live_vlan_ids - db_vlan_ids
        
    
    print(vlan_id_diff)

    #Basic stuff add vlan to DB if it isn't available as we normally add vlans via UI
    vlan_list_diff = [] #this is a list of dictionaries {'vlan_id': '100', 'vlan_name': 'auto-vlan'}
    for vlan_id, vlan_name in live_vlan_map.items():
        if vlan_id in vlan_id_diff:
            vlan_list_diff.append({'vlan_id': vlan_id, 'vlan_name': vlan_name})


    #Update DB with new vlans
    update_db = apiut.update_device_vlans_db(device_id, vlan_list_diff)
    current_job = get_current_job()
    session_id = current_job.meta.get("session_id")
    run_chain = current_job.meta.get("run_chain")
    if update_db and run_chain:
        log_to_ws(session_id, "Step 7: VLANs updated in database.")
        log_to_ws(session_id, f"\x1b[32m--- [COMPLETED] Provisioning completed ---\x1b[0m")
    else:
        log_to_ws(session_id, "Step 7: VLANs update FAILED.")

def set_trunk_interface_vlan_job(device_ip,interface_name,vlan_id):
    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()
        cu = Config(dev)
        commands = f"""
        set interfaces {interface_name} unit 0 family ethernet-switching interface-mode trunk
        set interfaces {interface_name} unit 0 family ethernet-switching vlan members {vlan_id}
        """        
        cu.load(commands,format="set")
        cu.commit(comment=f"Automation: set interface mode {interface_name} to {interface_mode}")
        dev.close()

        return {
            "status": "Success",
            "interface_name": interface_name,
            "interface_mode": interface_mode,
            "job_type" : "set_trunk_interface_vlan",
            "message": f"Interface {interface_name} successfully set to mode {interface_mode}."
        }    
    except Exception as e:
        return {
             "status": "Error",
             "device_ip": device_ip,
             "error": str(e)
        }
    
    

def set_interface_vlan_job(device_ip, interface, vlan_id):
    try:
        dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
        dev.open()
        logger.info(f"Set interface {interface} to VLAN {vlan_id} for device {device_ip}")
        cu = Config(dev)
        #set and del command might look stupid but if the config stanza is not available
        #it returns a warning/error. We avoid it by this trick.
        commands = f"""
        set interfaces {interface} unit 0 family ethernet-switching interface-mode access
        set interfaces {interface} unit 0 family ethernet-switching vlan members {vlan_id} 
        del interfaces {interface} unit 0 family ethernet-switching vlan 
        set interfaces {interface} unit 0 family ethernet-switching vlan members {vlan_id}
        """
        cu.load(commands,format="set")
        cu.commit(comment=f"Automation: Set interface {interface} to VLAN {vlan_id}")
        dev.close()

        job_id = get_current_job().get_id()      
        message = {
            "job_type": "set_interface_vlan",
            "device_ip": device_ip,
            "interface": interface,
            "vlan_id": vlan_id,
            "job_id": job_id
        }
        #r.publish("job_notifications", json.dumps(message))
        
        return {
            "status": "Success",
            "vlan_id": vlan_id,
            "job_type" : "set_interface_vlan",
            "message": f"Interface {interface} successfully set to VLAN {vlan_id}."
        }    
    except Exception as e:
        return {
             "status": "Error",
             "device_ip": device_ip,
             "error": str(e)
        }

def create_vlan_job(device_ip, vlan_id, vlan_name):
    """
       This function creates a VLAN on a Juniper device.
    """

    dev = Device(host=device_ip, user=DEVICE_USER, password=DEVICE_PASSWORD)
    try:
        dev.open()
        cu = Config(dev)
        commands = f"""
        set vlans auto-vlan-{vlan_id} vlan-id {vlan_id}
        """
        cu.load(commands,format="set")
        cu.commit(comment=f"Automation: Created VLAN {vlan_id}")
        dev.close()

        job_id = get_current_job().get_id()      
        message = {
            "job_type": "create_vlan",
            "device_ip": device_ip,
            "vlan_id": vlan_id,
            "job_id": job_id
        }
        logger.info(f"Created VLAN {vlan_id} for device {device_ip}")
        r.publish("job_notifications", json.dumps(message))
        
        return {
            "status": "Success",
            "vlan_id": vlan_id,
            "job_type" : "create_vlan",
            "message": f"VLAN {vlan_id} successfully created."
        }    

    except ConnectionError:
        logger.error(f"Could not connect to device {device_ip}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to the device"
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )
    