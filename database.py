import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
from typing import AsyncGenerator

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- SYNC SETUP WITH POOLING (For your RQ Workers) ---
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # Keep 10 connections open at all times
    max_overflow=20,        # If all 10 are busy, allow up to 20 temporary extra ones
    pool_timeout=30,        # Wait 30 seconds for a connection before failing
    pool_recycle=1800,      # Recycle connections older than 30 mins (prevents stale links)
    pool_pre_ping=True      # Check if the connection is alive before using it (VITAL)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        # In a pool, .close() just puts the connection back in the 'parking lot'
        db.close()

# --- ASYNC SETUP WITH POOLING (For your FastAPI Endpoints) ---
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

async_engine = create_async_engine(
    ASYNC_DATABASE_URL, 
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()

class Base(DeclarativeBase):
    pass