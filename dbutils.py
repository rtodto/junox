from sqlalchemy.sql._elements_constructors import bindparam
from .models import *
from .database import *
from sqlalchemy import update
from sqlalchemy.orm import Session
from .schemas import *

async def db_get_all_vlan_catalog_async(db: AsyncSessionLocal):
    """
    Fetch the entire global VLAN pool asynchronously.
    """
    # 1. Construct the select statement with explicit ordering
    stmt = select(VlanCatalog).order_by(VlanCatalog.vlan_id.asc())
    
    # 2. Execute the query and await the result
    result = await db.execute(stmt)
    
    # 3. Extract all objects into a Python list
    return result.scalars().all()


async def db_create_catalog_vlan_async(db: AsyncSession, vlan_data: VlanCreate):
    """
    Add a new standard VLAN to the Source of Truth asynchronously.
    """
    # 1. Instantiate the model
    db_vlan = VlanCatalog(
        vlan_id=vlan_data.vlan_id,
        name=vlan_data.name,
        description=vlan_data.description,
        category=vlan_data.category
    )
    
    # 2. Stage the object in the session
    db.add(db_vlan)
    
    # 3. Flush to the database (catches errors early and populates IDs)
    await db.flush()
    
    # 4. Commit the transaction
    await db.commit()
    
    # 5. Refresh to get the final state from the DB
    await db.refresh(db_vlan)
    
    return db_vlan