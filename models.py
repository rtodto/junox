from sqlalchemy import String, ForeignKey, Integer, BigInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base
from typing import List

class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    hostname: Mapped[str] = mapped_column(String(50), unique=True)
    ip_address: Mapped[str] = mapped_column(String(15))
    platform: Mapped[str] = mapped_column(String(20), default="juniper")
    type:  Mapped[str] = mapped_column(String(20)) #switch,router,firewall etc
    os_version: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(20))
    brand: Mapped[str] = mapped_column(String(20)) #cisco, juniper, paloalto etc


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

class MacTable(Base):
    __tablename__ = "mac_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(17))
    vlan_id: Mapped[int] = mapped_column(Integer)
    interface: Mapped[str] = mapped_column(String(50))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    device: Mapped["Device"] = relationship(back_populates="mac_entries")

class ArpTable(Base):
    __tablename__ = "arp_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip_address: Mapped[str] = mapped_column(String(15))
    mac_address: Mapped[str] = mapped_column(String(17))
    interface: Mapped[str] = mapped_column(String(50))
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    device: Mapped["Device"] = relationship(back_populates="arp_entries")

class RoutingTable(Base):
    __tablename__ = "routing_table"
    id: Mapped[int] = mapped_column(primary_key=True)
    destination: Mapped[str] = mapped_column(String(50)) # e.g., 10.0.0.0/24
    next_hop: Mapped[str] = mapped_column(String(50))    # e.g., 192.168.1.1 or 'ge-0/0/1.0'
    protocol: Mapped[str] = mapped_column(String(20))    # e.g., 'Static', 'OSPF', 'BGP'
    preference: Mapped[int] = mapped_column(Integer, nullable=True)
    age: Mapped[str] = mapped_column(String(20), nullable=True)

    # Link to the device
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"))
    device: Mapped["Device"] = relationship(back_populates="routing_entries")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)    