import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

# 1. Load your .env file
load_dotenv()

# 2. Get the connection string from environment variables
# Format: postgresql://user:password@localhost:5432/db_name
DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Create the SQLAlchemy Engine
# The 'engine' is the actual connection to the Postgres container
engine = create_engine(DATABASE_URL)

# 4. Create a SessionLocal class
# Each instance of SessionLocal will be a database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. The Base class for your models
# In SQLAlchemy 2.0+, we inherit from DeclarativeBase
class Base(DeclarativeBase):
    pass

# 6. Dependency for your FastAPI routes
# This ensures the connection is closed after every API request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()