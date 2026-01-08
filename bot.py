import os
import asyncpg
import tempfile
import matplotlib.pyplot as plt

from datetime import date, timedelta, datetime, time

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

client = OpenAI(api_key=OPENAI_API_KEY)
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
        "👋 Привет! Я бот для трекинга привычек 👇",
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
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done:{r['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{r['id']}"),
        )

        await message.answer(text, reply_markup=kb, parse_mode="HTML")


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

    streak = streak + 1 if last == today - timedelta(days=1) else 1

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id,
        today,
    )
    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
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
    await db.execute("UPDATE habits SET is_active=FALSE WHERE id=$1", habit_id)
    await db.close()
    await callback.message.edit_text("🗑 Привычка удалена")
    await callback.answer("Удалено")


# =========================
# STATS
# =========================

@dp.message_handler(lambda m: m.text == "📊 Статистика")
async def stats_cmd(message: types.Message):
    db = await get_db()

    habits = await db.fetch(
        """
        SELECT h.id FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        message.from_user.id,
    )

    if not habits:
        await message.answer("Нет данных для статистики")
        await db.close()
        return

    today = date.today()
    start = today - timedelta(days=6)

    logs = await db.fetch(
        """
        SELECT date, COUNT(*) cnt
        FROM habit_logs
        WHERE habit_id=ANY($1::int[])
        AND date BETWEEN $2 AND $3
        GROUP BY date ORDER BY date
        """,
        [h["id"] for h in habits],
        start,
        today,
    )

    days = [start + timedelta(days=i) for i in range(7)]
    values = {r["date"]: r["cnt"] for r in logs}
    counts = [values.get(d, 0) for d in days]

    plt.figure()
    plt.plot([d.strftime("%d.%m") for d in days], counts, marker="o")
    plt.grid(True)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(tmp.name)
    plt.close()

    await message.answer_photo(open(tmp.name, "rb"))
    await db.close()


# =========================
# AI ANALYSIS
# =========================

@dp.message_handler(lambda m: m.text == "🧠 AI-анализ")
async def ai_analysis(message: types.Message):
    if message.from_user.id in last_ai_call:
        await message.answer("⏳ Анализ доступен раз в сессию")
        return

    last_ai_call.add(message.from_user.id)

    db = await get_db()
    habits = await db.fetch(
        """
        SELECT title, streak FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        message.from_user.id,
    )
    await db.close()

    if not habits:
        await message.answer("Нет данных для анализа")
        return

    summary = "\n".join(
        f"- {h['title']}: серия {h['streak']} дней" for h in habits
    )

    prompt = f"""
Ты коуч по привычкам.

Привычки пользователя:
{summary}

Дай:
Итог (1–2 предложения)
2 совета
1 риск
"""

    await message.answer("🧠 Анализирую...")

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        await message.answer(response.output_text)
    except Exception as e:
        await message.answer("⚠️ AI временно недоступен")
        print("AI ERROR:", e)


# =========================
# REMINDERS
# =========================

@dp.message_handler(lambda m: m.text == "⏰ Напоминания")
async def reminder_help(message: types.Message):
    await message.answer(
        "⏰ Напоминания\n\n"
        "Установи:\n"
        "/timezone +3\n"
        "/reminder 21:00"
    )


@dp.message_handler(commands=["timezone"])
async def set_timezone(message: types.Message):
    try:
        offset = int(message.get_args())
    except:
        await message.answer("Пример: /timezone +3")
        return

    db = await get_db()
    await db.execute(
        "UPDATE users SET timezone_offset=$1 WHERE telegram_id=$2",
        offset,
        message.from_user.id,
    )
    await db.close()

    await message.answer(f"🌍 Часовой пояс: UTC{offset:+}")


@dp.message_handler(commands=["reminder"])
async def set_reminder(message: types.Message):
    try:
        reminder_time = datetime.strptime(message.get_args(), "%H:%M").time()
    except:
        await message.answer("Формат: /reminder 21:00")
        return

    db = await get_db()
    await db.execute(
        "UPDATE users SET reminder_time=$1 WHERE telegram_id=$2",
        reminder_time,
        message.from_user.id,
    )
    await db.close()

    await message.answer(f"⏰ Напоминание установлено на {reminder_time}")


async def send_reminders():
    now = datetime.utcnow()
    db = await get_db()

    users = await db.fetch(
        "SELECT telegram_id, reminder_time, timezone_offset FROM users WHERE reminder_time IS NOT NULL"
    )

    for u in users:
        local = (now + timedelta(hours=u["timezone_offset"])).time().replace(second=0)
        if local == u["reminder_time"]:
            await bot.send_message(
                u["telegram_id"],
                "⏰ Напоминание! Ты отметил привычки сегодня?",
            )

    await db.close()


# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()
    scheduler.add_job(send_reminders, "interval", minutes=1)
    scheduler.start()
    print("✅ Bot started successfully")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
