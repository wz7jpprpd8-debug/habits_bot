import os
import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

app = FastAPI()

# 🔓 CORS — обязательно для Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================
# DB
# ======================

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

# ======================
# MODELS
# ======================

class BaseReq(BaseModel):
    telegram_id: int

class AddHabitReq(BaseReq):
    title: str

class HabitActionReq(BaseReq):
    habit_id: int

# ======================
# HELPERS
# ======================

async def get_user_id(db, telegram_id: int) -> int:
    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        telegram_id,
    )
    if not user:
        user = await db.fetchrow(
            "INSERT INTO users (telegram_id) VALUES ($1) RETURNING id",
            telegram_id,
        )
    return user["id"]

# ======================
# ROUTES
# ======================

@app.post("/api/habits")
async def list_habits(req: BaseReq):
    db = await get_db()
    user_id = await get_user_id(db, req.telegram_id)

    rows = await db.fetch("""
        SELECT id, title, streak
        FROM habits
        WHERE user_id=$1 AND is_active=TRUE
        ORDER BY id
    """, user_id)

    await db.close()
    return [dict(r) for r in rows]


@app.post("/api/add")
async def add_habit(req: AddHabitReq):
    if len(req.title.strip()) < 2:
        return {"ok": False}

    db = await get_db()
    user_id = await get_user_id(db, req.telegram_id)

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user_id,
        req.title.strip(),
    )

    await db.close()
    return {"ok": True}


@app.post("/api/done")
async def mark_done(req: HabitActionReq):
    today = date.today()

    db = await get_db()
    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        req.habit_id,
    )

    if not habit:
        await db.close()
        return {"ok": False}

    if habit["last_completed"] == today:
        await db.close()
        return {"ok": True}

    streak = (
        habit["streak"] + 1
        if habit["last_completed"] == today.replace(day=today.day - 1)
        else 1
    )

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        req.habit_id,
        today,
    )
    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
        streak,
        today,
        req.habit_id,
    )

    await db.close()
    return {"ok": True}


@app.post("/api/delete")
async def delete_habit(req: HabitActionReq):
    db = await get_db()
    await db.execute(
        "UPDATE habits SET is_active=FALSE WHERE id=$1",
        req.habit_id,
    )
    await db.close()
    return {"ok": True}
