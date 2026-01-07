import asyncpg
from datetime import date, timedelta
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from openai import OpenAI
from datetime import datetime, timedelta

last_ai_call = {}

from config import BOT_TOKEN, DATABASE_URL


# =========================
# INIT
# =========================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
client = OpenAI()
import os



dp.middleware.setup(LoggingMiddleware())


# =========================
# DB HELPERS
# =========================

async def get_db():
    return await asyncpg.connect(DATABASE_URL)


async def init_db():
    conn = await get_db()
    with open("models.sql", "r", encoding="utf-8") as f:
        await conn.execute(f.read())
    await conn.close()


# =========================
# COMMANDS
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
        "Я бот для трекинга привычек.\n\n"
        "Команды:\n"
        "/add Название привычки\n"
        "/list — список привычек\n"
        "/stats — статистика\n"
    )


@dp.message_handler(commands=["add"])
async def add_habit(message: types.Message):
    title = message.get_args()
    if not title:
        await message.answer("Используй: /add Название привычки")
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

    await message.answer(f"✅ Привычка «{title}» добавлена")


@dp.message_handler(commands=["list"])
async def list_habits(message: types.Message):
    db = await get_db()
    rows = await db.fetch(
        """
        SELECT h.id, h.title, h.streak
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id = $1 AND h.is_active = TRUE
        ORDER BY h.created_at
        """,
        message.from_user.id
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

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "✅ Выполнено сегодня",
                callback_data=f"done:{r['id']}"
            )
        )

        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.message_handler(commands=["stats"])
async def stats_cmd(message: types.Message):
    db = await get_db()

    habits = await db.fetch(
        """
        SELECT h.id
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        message.from_user.id
    )

    if not habits:
        await message.answer("У тебя пока нет привычек 😔")
        await db.close()
        return

    today = date.today()
    start = today - timedelta(days=6)

    logs = await db.fetch(
        """
        SELECT date, COUNT(*) as cnt
        FROM habit_logs
        WHERE habit_id = ANY($1::int[])
          AND date BETWEEN $2 AND $3
        GROUP BY date
        ORDER BY date
        """,
        [h["id"] for h in habits],
        start,
        today
    )

    days = [start + timedelta(days=i) for i in range(7)]
    values = {row["date"]: row["cnt"] for row in logs}
    counts = [values.get(d, 0) for d in days]

    max_possible = len(habits) * 7
    completed = sum(counts)
    percent = int((completed / max_possible) * 100)

    await message.answer(
        "📊 <b>Статистика за 7 дней</b>\n\n"
        f"📌 Привычек: {len(habits)}\n"
        f"✅ Выполнений: {completed}/{max_possible}\n"
        f"📈 Выполнение: {percent}%",
        parse_mode="HTML"
    )

    plt.figure()
    plt.plot([d.strftime("%d.%m") for d in days], counts, marker="o")
    plt.grid(True)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(tmp.name)
    plt.close()

    await message.answer_photo(open(tmp.name, "rb"))
    await db.close()

@dp.message_handler(commands=["analysis"])
async def ai_analysis(message: types.Message):
    db = await get_db()

    uid = message.from_user.id
now = datetime.utcnow()

if uid in last_ai_call and now - last_ai_call[uid] < timedelta(minutes=10):
    await message.answer("⏳ Анализ можно запрашивать раз в 10 минут")
    return

last_ai_call[uid] = now

    habits = await db.fetch(
        """
        SELECT h.id, h.title
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id=$1 AND h.is_active=TRUE
        """,
        message.from_user.id
    )

    if not habits:
        await message.answer("Нет данных для анализа 😔")
        await db.close()
        return

    today = date.today()
    start = today - timedelta(days=13)

    logs = await db.fetch(
        """
        SELECT h.title, l.date
        FROM habit_logs l
        JOIN habits h ON h.id = l.habit_id
        WHERE l.habit_id = ANY($1::int[])
          AND l.date BETWEEN $2 AND $3
        ORDER BY l.date
        """,
        [h["id"] for h in habits],
        start,
        today
    )

    total_days = 14
    habit_count = len(habits)
    completed = len(logs)
    max_possible = habit_count * total_days
    percent = int((completed / max_possible) * 100)

    by_habit = {}
    for row in logs:
        by_habit.setdefault(row["title"], 0)
        by_habit[row["title"]] += 1

    summary = "\n".join(
        f"- {k}: {v}/{total_days} дней"
        for k, v in by_habit.items()
    )

    prompt = f"""
Ты — коуч по формированию привычек.

Данные пользователя за 14 дней:
- Привычек: {habit_count}
- Выполнений: {completed}/{max_possible}
- Процент выполнения: {percent}%

По привычкам:
{summary}

Сделай:
1. Краткий вывод (1–2 предложения)
2. 2 конкретных совета
3. Один риск, на который стоит обратить внимание

Пиши кратко, по делу, без воды.
"""

await message.answer("🧠 Анализирую твои привычки...")

try:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    await message.answer(response.output_text)

except Exception as e:
    await message.answer(
        "⚠️ Не удалось выполнить AI-анализ. Попробуй позже."
    )
    print("AI ERROR:", e)

    await db.close()
    
from openai import OpenAI
client = OpenAI()



        

# =========================
# CALLBACKS
# =========================

@dp.callback_query_handler(lambda c: c.data and c.data.split(":")[0] == "done")
async def mark_done(callback: types.CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    today = date.today()

    db = await get_db()

    exists = await db.fetchrow(
        "SELECT 1 FROM habit_logs WHERE habit_id=$1 AND date=$2",
        habit_id, today
    )

    if exists:
        await callback.answer("❌ Уже отмечено сегодня", show_alert=True)
        await db.close()
        return

    habit = await db.fetchrow(
        "SELECT streak, last_completed FROM habits WHERE id=$1",
        habit_id
    )

    last = habit["last_completed"]
    streak = habit["streak"]

    if last == today - timedelta(days=1):
        streak += 1
    else:
        streak = 1

    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id, today
    )

    await db.execute(
        "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
        streak, today, habit_id
    )

    await db.close()
    await callback.answer(f"🔥 Серия: {streak} дней", show_alert=True)


# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()
    print("✅ Bot started with inline buttons, streaks and stats")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
