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
from aiogram.types import WebAppInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not BOT_TOKEN or not DATABASE_URL:
    raise RuntimeError("ENV variables not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

scheduler = AsyncIOScheduler()
ai_client = OpenAI(api_key=OPENAI_API_KEY)


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

    # ✅ КНОПКА MINI APP (если URL реально есть)
    if WEBAPP_URL:
        kb.add(
            KeyboardButton(
                "🚀 Открыть приложение",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        )

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
        "👋 Привет!\n\n"
        "Это твой трекер привычек 👇",
        reply_markup=main_kb(),  # ← ВАЖНО
    )
# =========================
# ADD HABIT
# =========================

@dp.message_handler(lambda m: m.text == "➕ Добавить привычку")
async def add_habit_prompt(message: types.Message):
    await message.answer("✏️ Напиши название привычки")

@dp.message_handler(lambda m: m.text not in [
    "➕ Добавить привычку",
    "📋 Мои привычки",
    "📊 Статистика",
    "🧠 AI-анализ",
    "⏰ Напоминания",
] and not m.text.startswith("/"))
async def add_habit(message: types.Message):
    title = message.text.strip()
    if len(title) < 2:
        return

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

@dp.callback_query_handler(lambda c: c.data.startswith("done:"))
async def mark_done(callback: types.CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    today = date.today()

    db = await get_db()
    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        habit_id,
    )

    if habit["last_completed"] == today:
        await callback.answer("Уже отмечено сегодня")
        await db.close()
        return

    streak = habit["streak"] + 1 if habit["last_completed"] == today - timedelta(days=1) else 1

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id, today,
    )
    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
        streak, today, habit_id,
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
# STATS
# =========================

@dp.message_handler(lambda m: m.text == "📊 Статистика")
async def stats_cmd(message: types.Message):
    db = await get_db()
    habits = await db.fetch("""
        SELECT h.id
        FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
    """, message.from_user.id)

    if not habits:
        await message.answer("Нет данных")
        await db.close()
        return

    today = date.today()
    start = today - timedelta(days=6)

    logs = await db.fetch("""
        SELECT date, COUNT(*) cnt
        FROM habit_logs
        WHERE habit_id = ANY($1::int[])
        AND date BETWEEN $2 AND $3
        GROUP BY date
        ORDER BY date
    """, [h["id"] for h in habits], start, today)

    days = [start + timedelta(days=i) for i in range(7)]
    values = {row["date"]: row["cnt"] for row in logs}
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
    db = await get_db()
    habits = await db.fetch("""
        SELECT title, streak
        FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
    """, message.from_user.id)
    await db.close()

    if not habits:
        await message.answer("Нет данных для анализа")
        return

    summary = "\n".join(
        f"- {h['title']}: {h['streak']} дней"
        for h in habits
    )

    prompt = f"""
Ты коуч по привычкам.

Привычки пользователя:
{summary}

Дай краткий анализ и 2 совета.
"""

    await message.answer("🧠 Анализирую...")

    try:
        r = ai_client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        await message.answer(r.output_text)
    except Exception as e:
        await message.answer("AI временно недоступен")
        print("AI ERROR:", e)


# =========================
# REMINDERS
# =========================

@dp.message_handler(lambda m: m.text == "⏰ Напоминания")
async def reminder_help(message: types.Message):
    await message.answer(
        "⏰ Напоминания\n\n"
        "/timezone +3 — часовой пояс\n"
        "/reminder 21:00 — время напоминания",
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
        offset, message.from_user.id,
    )
    await db.close()

    await message.answer(f"🌍 Часовой пояс: UTC{offset:+}")

@dp.message_handler(commands=["reminder"])
async def set_reminder(message: types.Message):
    try:
        t = datetime.strptime(message.get_args(), "%H:%M").time()
    except:
        await message.answer("Формат: /reminder 21:00")
        return

    db = await get_db()
    await db.execute(
        "UPDATE users SET reminder_time=$1 WHERE telegram_id=$2",
        t, message.from_user.id,
    )
    await db.close()

    await message.answer(f"⏰ Напоминание установлено на {t.strftime('%H:%M')}")

async def send_reminders():
    utc_now = datetime.utcnow()
    today = utc_now.date()

    db = await get_db()
    users = await db.fetch("""
        SELECT telegram_id, timezone_offset, reminder_time, last_reminder
        FROM users
        WHERE reminder_time IS NOT NULL
    """)

    for u in users:
        local_time = (
            utc_now + timedelta(hours=u["timezone_offset"])
        ).time().replace(second=0, microsecond=0)

        if local_time == u["reminder_time"] and u["last_reminder"] != today:
            try:
                await bot.send_message(
                    u["telegram_id"],
                    "⏰ Напоминание!\nТы отметил привычки сегодня?",
                )
                await db.execute(
                    "UPDATE users SET last_reminder=$1 WHERE telegram_id=$2",
                    today, u["telegram_id"],
                )
            except Exception as e:
                print("Reminder error:", e)

    await db.close()


# =========================
# STARTUP
# =========================

async def on_startup(_):
    await init_db()
    scheduler.add_job(send_reminders, "interval", minutes=1)
    scheduler.start()
    print("✅ Bot started with habits, stats, AI and reminders")

if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
    )
