import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession # New imports
from dotenv import load_dotenv
from typing import AsyncGenerator

# 1. Load your .env file
load_dotenv()

# 2. Get the connection string from environment variables
# Format: postgresql://user:password@localhost:5432/db_name
DATABASE_URL = os.getenv("DATABASE_URL")

# --- EXISTING SYNC SETUP (Don't touch this) ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- NEW ASYNC SETUP (For Dashboard/High Performance) ---
# We transform 'postgresql://' to 'postgresql+asyncpg://' for the async engine
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
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

# --- SHARED BASE ---
class Base(DeclarativeBase):
    pass