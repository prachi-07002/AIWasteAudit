"""Create all tables. Run once after setting DATABASE_URL in .env.

Usage:
    python scripts/init_db.py
"""
from waste_audit.db.models import Base
from waste_audit.db.session import engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Tables created.")
