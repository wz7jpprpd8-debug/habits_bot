from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import os
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB ----------

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

# ---------- UI ----------

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

# ---------- API ----------

@app.post("/api/habits")
async def habits(data: dict):
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return []

    db = await get_db()

    rows = await db.fetch("""
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON u.id = h.user_id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.id
    """, telegram_id)

    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/add")
async def add_habit(data: dict):
    telegram_id = data.get("telegram_id")
    title = (data.get("title") or "").strip()

    if not telegram_id or len(title) < 2:
        return {"ok": False}

    db = await get_db()

    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        telegram_id
    )

    if not user:
        await db.close()
        return {"ok": False}

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user["id"], title
    )

    await db.close()
    return {"ok": True}

@app.post("/api/done")
async def done(data: dict):
    habit_id = data.get("habit_id")
    if not habit_id:
        return {"ok": False}

    today = date.today()
    db = await get_db()

    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        habit_id
    )

    if not habit:
        await db.close()
        return {"ok": False}

    # уже отмечено сегодня
    if habit["last_completed"] == today:
        await db.close()
        return {"ok": True}

    streak = (
        habit["streak"] + 1
        if habit["last_completed"] == today - timedelta(days=1)
        else 1
    )

    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
        streak, today, habit_id
    )

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id, today
    )

    await db.close()
    return {"ok": True}

@app.post("/api/delete")
async def delete(data: dict):
    habit_id = data.get("habit_id")
    if not habit_id:
        return {"ok": False}

    db = await get_db()
    await db.execute(
        "UPDATE habits SET is_active=FALSE WHERE id=$1",
        habit_id
    )
    await db.close()

    return {"ok": True}
