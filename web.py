from fastapi import FastAPI
from pydantic import BaseModel
import asyncpg
import os
from datetime import date

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

class User(BaseModel):
    telegram_id: int

class HabitAction(BaseModel):
    telegram_id: int
    habit_id: int

@app.post("/api/habits")
async def habits(data: User):
    db = await get_db()
    rows = await db.fetch("""
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.id
    """, data.telegram_id)
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/done")
async def done(data: HabitAction):
    today = date.today()
    db = await get_db()
    await db.execute(
        "UPDATE habits SET streak=streak+1, last_completed=$1 WHERE id=$2",
        today, data.habit_id,
    )
    await db.close()
    return {"ok": True}

@app.post("/api/delete")
async def delete(data: HabitAction):
    db = await get_db()
    await db.execute(
        "UPDATE habits SET is_active=FALSE WHERE id=$1",
        data.habit_id,
    )
    await db.close()
    return {"ok": True}
