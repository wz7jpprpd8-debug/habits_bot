
import asyncpg
from config import DATABASE_URL

async def get_db():
    return await asyncpg.connect(DATABASE_URL)
