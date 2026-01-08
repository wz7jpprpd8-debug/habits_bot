import os
import asyncpg
import tempfile
import matplotlib.pyplot as plt

from datetime import date, timedelta, datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

client = OpenAI()
scheduler = AsyncIOScheduler()

waiting_for_habit_name = set()
last_ai_call = set()


# =========================
# MAIN MENU
# =========================

main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(
    KeyboardButton("➕ Добавить привычку"),
    KeyboardButton("📋 Мои привычки"),
)
main_menu.add(
    KeyboardButton("📊 Статистика"),
    KeyboardButton("🧠 AI-анализ"),
)
main_menu.add(
    KeyboardButton("⏰ Напоминания"),
)


# =========================
# DB
# =========================

async def get_db():
    return await asyncpg.connect(DATABASE_URL)


async def init_db():
    conn = await get_db()
    with open("models.sql", "r", encoding="utf-8") as f:
        await conn.execute(f.read())
    await conn.close()


# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    db = await get_db()
    await db.execute(
        """
        INSERT INTO users (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO NOTHING
        """,
        message.from_user.id,
        message.from_user.username,
    )
    await db.close()

    await message.answer(
        "👋 Привет!\n\n"
        "Я бот для трекинга привычек 👇",
        reply_markup=main_menu,
    )


# =========================
# ADD HABIT
# =========================

@dp.message_handler(lambda m: m.text == "➕ Добавить привычку")
async def add_habit_button(message: types.Message):
    waiting_for_habit_name.add(message.from_user.id)
    await message.answer("✏️ Напиши название привычки")


@dp.message_handler(lambda m: m.from_user.id in waiting_for_habit_name)
async def catch_habit_name(message: types.Message):
    title = message.text.strip()
    waiting_for_habit_name.remove(message.from_user.id)

    db = await get_db()
    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        message.from_user.id,
    )

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user["id"],
        title,
    )
    await db.close()

    await message.answer(
        f"✅ Привычка «{title}» добавлена",
        reply_markup=main_menu,
    )


# =========================
# LIST HABITS
# =========================

@dp.message_handler(lambda m: m.text == "📋 Мои привычки" or m.text == "/list")
async def list_habits(message: types.Message):
    db = await get_db()
    rows = await db.fetch(
        """
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.created_at
        """,
        message.from_user.id,
    )
    await db.close()

    if not rows:
        await message.answer("У тебя пока нет привычек")
        return

    for r in rows:
        text = (
            f"📌 <b>{r['title']}</b>\n"
            f"🔥 Серия: {r['streak']} дней"
        )

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(
                "✅ Выполнено",
                callback_data=f"done:{r['id']}",
            ),
            InlineKeyboardButton(
                "🗑 Удалить",
                callback_data=f"delete:{r['id']}",
            ),
        )

        await message.answer(
            text,
            reply_markup=kb,
            parse_mode="HTML",
        )


# =========================
# CALLBACKS
# =========================

@dp.callback_query_handler(lambda c: c.data.startswith("done:"))
async def mark_done(callback: types.CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    today = date.today()

    db = await get_db()

    exists = await db.fetchrow(
        "SELECT 1 FROM habit_logs WHERE habit_id=$1 AND date=$2",
        habit_id,
        today,
    )

    if exists:
        await callback.answer("Уже отмечено сегодня")
        await db.close()
        return

    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        habit_id,
    )

    streak = habit["streak"]
    last = habit["last_completed"]

    if last == today - timedelta(days=1):
        streak += 1
    else:
        streak = 1

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id,
        today,
    )

    await db.execute(
        """
        UPDATE habits
        SET streak=$1, last_completed=$2
        WHERE id=$3
        """,
        streak,
        today,
        habit_id,
    )

    await db.close()
    await callback.answer(f"🔥 Серия: {streak} дней", show_alert=True)


@dp.callback_query_handler(lambda c: c.data.startswith("delete:"))
async def delete_habit(callback: types.CallbackQuery):
    habit_id = int(callback.data.split(":")[1])

    db = await get_db()
    await db.execute(
        "UPDATE habits SET is_active=FALSE WHERE id=$1",
        habit_id,
    )
    await db.close()

    await callback.message.edit_text("🗑 Привычка удалена")
    await callback.answer("Удалено")


# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()
    print("✅ Bot started successfully")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
