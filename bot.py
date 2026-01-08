import os
import asyncpg
import tempfile
import matplotlib.pyplot as plt

from datetime import date, timedelta, datetime, time

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from openai import OpenAI

from aiohttp import web


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 8080))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

client = OpenAI(api_key=OPENAI_API_KEY)
scheduler = AsyncIOScheduler()

# aiohttp
routes = web.RouteTableDef()


# =========================
# FSM
# =========================

class AddHabitFSM(StatesGroup):
    title = State()
    reminder_choice = State()
    reminder_time = State()


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

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(
                url="https://storied-bubblegum-a94e6a.netlify.app"
            )
        )
    )

    await message.answer(
        "👋 Привет!\n\n"
        "Это твой трекер привычек.\n"
        "Открывай приложение 👇",
        reply_markup=kb,
    )


# =========================
# ADD HABIT (FSM WIZARD)
# =========================

@dp.message_handler(lambda m: m.text == "➕ Добавить привычку")
async def add_habit_start(message: types.Message):
    await AddHabitFSM.title.set()
    await message.answer(
        "✏️ Введите название привычки",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message_handler(state=AddHabitFSM.title)
async def add_habit_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⏰ Да", "❌ Нет")

    await AddHabitFSM.reminder_choice.set()
    await message.answer(
        "⏰ Нужны напоминания?",
        reply_markup=kb,
    )


@dp.message_handler(state=AddHabitFSM.reminder_choice)
async def add_habit_reminder_choice(message: types.Message, state: FSMContext):
    if message.text == "❌ Нет":
        await save_habit(state, message)
        return

    if message.text == "⏰ Да":
        await AddHabitFSM.reminder_time.set()
        await message.answer(
            "Введите время (HH:MM, например 21:00)",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer("Пожалуйста, выберите вариант кнопкой")


@dp.message_handler(state=AddHabitFSM.reminder_time)
async def add_habit_reminder_time(message: types.Message, state: FSMContext):
    try:
        t = datetime.strptime(message.text, "%H:%M").time()
    except ValueError:
        await message.answer("❌ Формат времени: HH:MM (пример: 21:00)")
        return

    await state.update_data(reminder_time=t)
    await save_habit(state, message)


async def save_habit(state: FSMContext, message: types.Message):
    data = await state.get_data()

    db = await get_db()
    user = await db.fetchrow(
        "SELECT id FROM users WHERE telegram_id=$1",
        message.from_user.id,
    )

    await db.execute(
        """
        INSERT INTO habits (user_id, title, reminder_time)
        VALUES ($1, $2, $3)
        """,
        user["id"],
        data["title"],
        data.get("reminder_time"),
    )

    await db.close()
    await state.finish()

    await message.answer(
        f"✅ Привычка «{data['title']}» добавлена",
        reply_markup=main_menu,
    )


# =========================
# LIST / DONE / DELETE
# =========================

@dp.message_handler(lambda m: m.text == "📋 Мои привычки")
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
        await message.answer("Пока нет привычек")
        return

    for r in rows:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✅ Выполнено", callback_data=f"done:{r['id']}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{r['id']}"),
        )

        await message.answer(
            f"📌 <b>{r['title']}</b>\n🔥 Серия: {r['streak']}",
            parse_mode="HTML",
            reply_markup=kb,
        )


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

    streak = habit["streak"] + 1 if habit["last_completed"] == today - timedelta(days=1) else 1

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
    await callback.answer(f"🔥 Серия: {streak}", show_alert=True)


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

    habits = await db.fetch(
        """
        SELECT h.id
        FROM habits h
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
        WHERE habit_id = ANY($1::int[])
        AND date BETWEEN $2 AND $3
        GROUP BY date
        ORDER BY date
        """,
        [h["id"] for h in habits],
        start,
        today,
    )

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
    habits = await db.fetch(
        """
        SELECT title, streak
        FROM habits h
        JOIN users u ON h.user_id=u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        message.from_user.id,
    )
    await db.close()

    if not habits:
        await message.answer("Нет данных для анализа")
        return

    summary = "\n".join(f"- {h['title']}: {h['streak']} дней" for h in habits)

    prompt = f"""
Ты коуч по привычкам.

Привычки пользователя:
{summary}

Дай краткий анализ и 2 практических совета.
"""

    await message.answer("🧠 Анализирую...")

    try:
        r = client.responses.create(
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

async def send_reminders():
    now = datetime.utcnow().time().replace(second=0, microsecond=0)

    db = await get_db()
    users = await db.fetch(
        """
        SELECT DISTINCT u.telegram_id
        FROM users u
        JOIN habits h ON h.user_id=u.id
        WHERE h.reminder_time=$1 AND h.is_active=TRUE
        """,
        now,
    )

    for u in users:
        try:
            await bot.send_message(
                u["telegram_id"],
                "⏰ Напоминание! Отметь привычки 👇",
            )
        except Exception as e:
            print("Reminder error:", e)

    await db.close()


# =========================
# MINI APP API
# =========================

@routes.post("/api/habits")
async def api_habits(request):
    data = await request.json()
    telegram_id = data["telegram_id"]

    db = await get_db()
    rows = await db.fetch(
        """
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        telegram_id,
    )
    await db.close()

    return web.json_response([
        {
            "id": r["id"],        # 🔴 ОБЯЗАТЕЛЬНО
            "title": r["title"],
            "streak": r["streak"]
        }
        for r in rows
    ])


# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()

    app = web.Application()
    app.add_routes(routes)   # ← ОДИН РАЗ

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    scheduler.add_job(send_reminders, "interval", minutes=1)
    scheduler.start()

    print("✅ Bot + API started")


if __name__ == "__main__":
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
    )
