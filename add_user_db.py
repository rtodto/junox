from database import SessionLocal
from models import User
from auth import hash_password

def create_admin_user():
    db = SessionLocal()
    try:
        # 1. Define your credentials
        username = "admin"
        password = "lab123"
        
        # 2. Check if user already exists
        exists = db.query(User).filter(User.username == username).first()
        if exists:
            print(f"User '{username}' already exists.")
            return

        # 3. Hash the password and create the user object
        new_user = User(
            username=username,
            hashed_password=hash_password(password) # This scrambles the password
        )

        db.add(new_user)
        db.commit()
        print(f"User '{username}' created successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()