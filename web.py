from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
import os
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

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
    db = await get_db()
    rows = await db.fetch("""
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON u.id = h.user_id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.id
    """, data["telegram_id"])
    await db.close()
    return [dict(r) for r in rows]

@app.post("/api/add")
async def add(data: dict):
    db = await get_db()
    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        data["telegram_id"]
    )
    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user["id"], data["title"]
    )
    await db.close()
    return {"ok": True}

@app.post("/api/done")
async def done(data: dict):
    db = await get_db()
    today = date.today()

    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        data["habit_id"]
    )

    streak = habit["streak"] + 1 if habit["last_completed"] == today - timedelta(days=1) else 1

    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
        streak, today, data["habit_id"]
    )
    await db.close()
    return {"ok": True}

@app.post("/api/delete")
async def delete(data: dict):
    db = await get_db()
    await db.execute(
        "UPDATE habits SET is_active=FALSE WHERE id=$1",
        data["habit_id"]
    )
    await db.close()
    return {"ok": True}
