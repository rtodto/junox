from models import DeviceNet, MacTable, ArpTable, RoutingTable
from database import SessionLocal

def seed_data():
    db = SessionLocal()

    try:
        # 1. Create the Device with your new fields
        new_device = DeviceNet(
            hostname="vswitch1",
            ip_address="192.168.120.10",
            platform="juniper",
            type="router",           # New field
            os_version="25.4R1.12",  # New field
            model="ex9214",           # New field
            brand="juniper"          # New field
        )
        
        db.add(new_device)
        db.flush()  # Push to DB to get the ID back

        # 2. Add a Routing Entry (Specific to a Router)
        route = RoutingTable(
            destination="10.255.0.0/24",
            next_hop="172.16.1.1",
            protocol="BGP",
            preference=170,
            device_id=new_device.id
        )

        # 3. Add an ARP Entry
        arp = ArpTable(
            ip_address="172.16.1.1",
            mac_address="00:11:22:33:44:55",
            interface="xe-0/0/0.0",
            device_id=new_device.id
        )

        db.add_all([route, arp])
        db.commit()
        print(f"Successfully created {new_device.brand} {new_device.model} ({new_device.hostname})")

    except Exception as e:
        print(f"Error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()