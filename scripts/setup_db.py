"""Initialize the VetFlow database."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import Database


async def main():
    db = Database("data/vetflow.db")
    await db.connect()
    await db.run_migrations()
    print("Database initialized successfully!")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
