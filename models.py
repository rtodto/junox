from sqlalchemy import DateTime, String, ForeignKey, Integer, BigInteger, Boolean,UniqueConstraint,Column,Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base
from typing import List
from datetime import datetime

class DeviceNet(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(50), unique=True)
    ip_address: Mapped[str] = mapped_column(String(15))
    platform: Mapped[str] = mapped_column(String(20), default="juniper")
    type:  Mapped[str] = mapped_column(String(20)) #switch,router,firewall etc
    os_version: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(20))
    vendor: Mapped[str] = mapped_column(String(20), nullable=False, server_default="Generic") #cisco, juniper, paloalto etc
    serialnumber: Mapped[str] = mapped_column(String(20) , nullable=False ,server_default="XXXXXX")
    sync_status: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False)
    last_synced: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Relationships with Cascading Deletes
    mac_entries: Mapped[List["MacTable"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    arp_entries: Mapped[List["ArpTable"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    routing_entries: Mapped[List["RoutingTable"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    vlans: Mapped[List["VLANs"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    eth_interfaces_entries: Mapped[List["EthInterfaces"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )

class EthInterfaces(Base):
    __tablename__ = "eth_interfaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    interface_name: Mapped[str] = mapped_column(String(50))
    oper_status: Mapped[str] = mapped_column(String(50))
    admin_status: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(50),nullable=True)
    mac_address: Mapped[str] = mapped_column(String(17))
    interface_tagness: Mapped[str] = mapped_column(String(50),nullable=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    device: Mapped["DeviceNet"] = relationship(back_populates="eth_interfaces_entries")

    #we want uniqueness with interface name and device id
    __table_args__ = (
        UniqueConstraint("device_id", "interface_name", name="uq_device_interface"),
    )

class MacTable(Base):
    __tablename__ = "mac_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(17))
    vlan_id: Mapped[int] = mapped_column(Integer)
    interface: Mapped[str] = mapped_column(String(50))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    device: Mapped["DeviceNet"] = relationship(back_populates="mac_entries")

class VLANs(Base):
    __tablename__ = "vlans"
    id: Mapped[int] = mapped_column(primary_key=True)
    vlan_id: Mapped[int] = mapped_column(Integer)
    vlan_name: Mapped[str] = mapped_column(String(50))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    device: Mapped["DeviceNet"] = relationship(back_populates="vlans")
    
class VlanCatalog(Base):
    __tablename__ = "vlan_catalog"

    id = Column(Integer, primary_key=True, index=True)
    vlan_id = Column(Integer, unique=True, nullable=False, index=True) 
    name = Column(String(50), nullable=False)                         
    description = Column(Text, nullable=True)                         
    category = Column(String(30), nullable=True)

class ArpTable(Base):
    __tablename__ = "arp_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip_address: Mapped[str] = mapped_column(String(15))
    mac_address: Mapped[str] = mapped_column(String(17))
    interface: Mapped[str] = mapped_column(String(50))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    device: Mapped["DeviceNet"] = relationship(back_populates="arp_entries")

class RoutingTable(Base):
    __tablename__ = "routing_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    destination: Mapped[str] = mapped_column(String(50)) # e.g., 10.0.0.0/24
    next_hop: Mapped[str] = mapped_column(String(50))    # e.g., 192.168.1.1 or 'ge-0/0/1.0'
    protocol: Mapped[str] = mapped_column(String(20))    # e.g., 'Static', 'OSPF', 'BGP'
    preference: Mapped[int] = mapped_column(Integer, nullable=True)
    age: Mapped[str] = mapped_column(String(20), nullable=True)

    # Link to the device
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    device: Mapped["DeviceNet"] = relationship(back_populates="routing_entries")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)    