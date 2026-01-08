import os
import asyncpg
import tempfile
import matplotlib.pyplot as plt

from datetime import date, timedelta, datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils import executor

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN or not DATABASE_URL:
    raise RuntimeError("ENV variables not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()
ai_client = OpenAI(api_key=OPENAI_API_KEY)

# 🔑 состояние ожидания ввода привычки
waiting_for_habit = set()


# =========================
# DB
# =========================

async def get_db():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    db = await get_db()
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        timezone_offset INT DEFAULT 0,
        reminder_time TIME,
        last_reminder DATE
    );

    CREATE TABLE IF NOT EXISTS habits (
        id SERIAL PRIMARY KEY,
        user_id INT,
        title TEXT,
        streak INT DEFAULT 0,
        last_completed DATE,
        is_active BOOLEAN DEFAULT TRUE
    );

    CREATE TABLE IF NOT EXISTS habit_logs (
        id SERIAL PRIMARY KEY,
        habit_id INT,
        date DATE
    );
    """)
    await db.close()


# =========================
# KEYBOARD
# =========================

def main_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        KeyboardButton("➕ Добавить привычку"),
        KeyboardButton("📋 Мои привычки"),
    )
    kb.add(
        KeyboardButton("📊 Статистика"),
        KeyboardButton("🧠 AI-анализ"),
    )
    kb.add(
        KeyboardButton("⏰ Напоминания"),
    )
    return kb


# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    db = await get_db()
    await db.execute(
        "INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING",
        message.from_user.id,
    )
    await db.close()

    await message.answer(
        "👋 Привет!\nЯ бот для трекинга привычек 👇",
        reply_markup=main_kb(),
    )


# =========================
# ADD HABIT (FIXED)
# =========================

@dp.message_handler(lambda m: m.text == "➕ Добавить привычку")
async def add_habit_prompt(message: types.Message):
    waiting_for_habit.add(message.from_user.id)
    await message.answer("✏️ Напиши название привычки")

@dp.message_handler()
async def add_habit(message: types.Message):
    uid = message.from_user.id

    # ❗ добавляем привычку ТОЛЬКО если ждали её
    if uid not in waiting_for_habit:
        return

    waiting_for_habit.remove(uid)
    title = message.text.strip()

    if title.startswith("/") or len(title) < 2:
        await message.answer("❌ Некорректное название", reply_markup=main_kb())
        return

    db = await get_db()
    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        uid,
    )

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user["id"],
        title,
    )
    await db.close()

    await message.answer(
        f"✅ Привычка «{title}» добавлена",
        reply_markup=main_kb(),
    )


# =========================
# LIST HABITS
# =========================

@dp.message_handler(lambda m: m.text == "📋 Мои привычки")
async def list_habits(message: types.Message):
    db = await get_db()
    rows = await db.fetch("""
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.id
    """, message.from_user.id)
    await db.close()

    if not rows:
        await message.answer("Пока нет привычек 🙂")
        return

    for r in rows:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done:{r['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{r['id']}"),
        )

        await message.answer(
            f"📌 <b>{r['title']}</b>\n🔥 Серия: {r['streak']} дней",
            parse_mode="HTML",
            reply_markup=kb,
        )


# =========================
# CALLBACKS
# =========================

@dp.callback_query_handler(lambda c: c.data.startswith
