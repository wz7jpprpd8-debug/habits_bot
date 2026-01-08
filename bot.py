import os
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

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
        telegram_id BIGINT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS habits (
        id SERIAL PRIMARY KEY,
        user_id INT,
        title TEXT,
        streak INT DEFAULT 0,
        is_active BOOLEAN DEFAULT TRUE
    );
    """)
    await db.close()

# =========================
# KEYBOARD
# =========================

def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        KeyboardButton("➕ Добавить привычку"),
        KeyboardButton("📋 Мои привычки"),
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
        message.from_user.id
    )
    await db.close()

    await message.answer(
        "👋 Привет!\n\nЯ бот для трекинга привычек.",
        reply_markup=main_keyboard()
    )

# =========================
# ADD HABIT
# =========================

@dp.message_handler(lambda m: m.text == "➕ Добавить привычку")
async def ask_habit_name(message: types.Message):
    await message.answer("Напиши название привычки ✏️")

@dp.message_handler(lambda m: m.text not in [
    "➕ Добавить привычку",
    "📋 Мои привычки"
])
async def save_habit(message: types.Message):
    title = message.text.strip()

    if len(title) < 2:
        await message.answer("Название слишком короткое")
        return

    db = await get_db()

    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        message.from_user.id
    )

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user["id"], title
    )

    await db.close()

    await message.answer(
        f"✅ Привычка «{title}» добавлена",
        reply_markup=main_keyboard()
    )

# =========================
# LIST HABITS
# =========================

@dp.message_handler(lambda m: m.text == "📋 Мои привычки")
async def list_habits(message: types.Message):
    db = await get_db()

    rows = await db.fetch("""
        SELECT title, streak
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        ORDER BY h.id
    """, message.from_user.id)

    await db.close()

    if not rows:
        await message.answer("У тебя пока нет привычек 🙂")
        return

    text = "📋 <b>Мои привычки</b>\n\n"
    for r in rows:
        text += f"• {r['title']} — 🔥 {r['streak']} дней\n"

    await message.answer(text, parse_mode="HTML")

# =========================
# FALLBACK
# =========================

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer(
        "Используй кнопки ниже 👇",
        reply_markup=main_keyboard()
    )

# =========================
# STARTUP
# =========================

async def on_startup(_):
    await init_db()
    print("✅ Bot started")

if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup
    )
