from sqlalchemy.sql._elements_constructors import bindparam
from .models import *
from .database import SessionLocal
from sqlalchemy import update
from sqlalchemy.orm import Session
from .schemas import *

def db_get_all_vlan_catalog(db: Session):
    """Fetch the entire global VLAN pool."""
    return db.query(VlanCatalog).order_by(VlanCatalog.vlan_id.asc()).all()


def db_create_catalog_vlan(db: Session,vlan_data: VlanCreate):
    """Add a new standard VLAN to the Source of Truth."""
    
    db_vlan = VlanCatalog(
        vlan_id=vlan_data.vlan_id,
        name=vlan_data.name,
        description=vlan_data.description,
        category=vlan_data.category
    )
    db.add(db_vlan)
    db.commit()
    db.refresh(db_vlan)
    return db_vlan