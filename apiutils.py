
from database import SessionLocal
from models import * 

class APIUtils:
    def __init__(self):
        self.db = SessionLocal()

    def device_id_to_ip(self, device_id: int):
        """
        We take device_id as input and we return the IP address of the device 
        """
        device = self.db.query(DeviceNet).filter(DeviceNet.id==device_id).first()

        if not device:
            return None
        
        return device.ip_address

    def add_device_to_db(self, device: DeviceNet):
        try:
            self.db.add(device)
            self.db.commit()
            return device
        except Exception as e:
            self.db.rollback()
            raise e
  
    def get_device_vlans(self, device_id: int):
        """
        We take device_id as input and we return the vlans of the device 
        """
        device = self.db.query(VLANs).filter(VLANs.device_id==device_id).all()
        #number of vlans
        num_vlans = len(device)

        if not device:
            return None
        
        return device

    def update_device_vlans_db(self,device_id: int, vlan_diff: list):
        """
        We take device_id and vlan_diff as input and we update the vlans of the device on DB
        """
        #Add new vlans
        for vlan in vlan_diff:
            new_vlan = VLANs(device_id=device_id, vlan_id=vlan['vlan_id'], vlan_name=vlan['vlan_name'])
            self.db.add(new_vlan)
        self.db.commit()

        return True
    