# ============================================================
# backend/seed.py
# Seeds the database with initial mock data for development.
#
# WHY: fresh DBs start empty. We need at least the 3 role users to
# test login + RBAC without registering accounts by hand every time.
#
# Run:  python seed.py   (from backend/, venv active)
# Idempotent: safe to run multiple times (skips existing usernames).
# ============================================================

import os
import sys

# Ensure we can import backend modules (database, models, security)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine, Base  # noqa: E402
from models import User  # noqa: E402
from security.auth import hash_password  # noqa: E402
from security.models import Role  # noqa: E402


MOCK_USERS = [
    {
        "username": "admin",
        "email": "admin@medassist.local",
        "password": "admin123",
        "role": Role.ADMIN.value,
    },
    {
        "username": "expert1",
        "email": "expert1@medassist.local",
        "password": "expert123",
        "role": Role.EXPERT.value,
    },
    {
        "username": "nurse1",
        "email": "nurse1@medassist.local",
        "password": "nurse123",
        "role": Role.END_USER.value,
    },
]


def seed() -> None:
    print("Creating tables if they don't exist...")
    # In normal flow Alembic creates tables. This is a fallback so the
    # skill can also run standalone without the migration step.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for u in MOCK_USERS:
            exists = db.query(User).filter(User.username == u["username"]).first()
            if exists:
                print(f"  - skip {u['username']} (already exists)")
                continue
            # CRITICAL: hash the password. NEVER store plaintext.
            db.add(
                User(
                    username=u["username"],
                    email=u["email"],
                    password_hash=hash_password(u["password"]),
                    role=u["role"],
                )
            )
            print(f"  + created {u['username']} ({u['role']})")
        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
