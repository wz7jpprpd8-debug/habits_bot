import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import date
from datetime import timedelta

from config import BOT_TOKEN, DATABASE_URL


# =========================
# INIT
# =========================
print("DEBUG BOT_TOKEN repr:", repr(BOT_TOKEN))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())


# =========================
# DB INIT
# =========================

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    with open("models.sql", "r", encoding="utf-8") as f:
        await conn.execute(f.read())
    await conn.close()


async def get_db():
    return await asyncpg.connect(DATABASE_URL)


# =========================
# HANDLERS
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
        "/add Название\n"
        "/list\n"
        "/ai — AI-анализ"
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
        user["id"],
        title
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
        text = f"📌 <b>{r['title']}</b>\n🔥 Серия: {r['streak']} дней"

        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                "✅ Выполнено сегодня",
                callback_data=f"done:{r['id']}"
            )
        )

        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.message_handler(commands=["ai"])
async def ai_stub(message: types.Message):
    await message.answer(
        "🧠 AI-анализ будет подключён следующим шагом.\n"
        "Сейчас проверяем стабильный запуск 😉"
    )
@dp.callback_query_handler(lambda c: c.data.startswith("done:"))
async def mark_done(callback: types.CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    today = date.today()

    db = await get_db()

    # Проверка: уже отмечено сегодня?
    exists = await db.fetchrow(
        """
        SELECT 1 FROM habit_logs
        WHERE habit_id = $1 AND date = $2
        """,
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

    streak = habit["streak"]
    last = habit["last_completed"]

    if last == today - timedelta(days=1):
        streak += 1
    else:
        streak = 1

    # Запись лога
    await db.execute(
        "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
        habit_id, today
    )

    # Обновление привычки
    await db.execute(
        """
        UPDATE habits
        SET streak=$1, last_completed=$2
        WHERE id=$3
        """,
        streak, today, habit_id
    )

    await db.close()

    await callback.answer(f"🔥 Серия: {streak} дней", show_alert=True)

# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()
    print("✅ Bot started and DB initialized")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
