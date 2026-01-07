import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

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
        SELECT h.id, h.title
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

    text = "📌 Твои привычки:\n\n"
    for r in rows:
        text += f"{r['id']}. {r['title']}\n"

    await message.answer(text)


@dp.message_handler(commands=["ai"])
async def ai_stub(message: types.Message):
    await message.answer(
        "🧠 AI-анализ будет подключён следующим шагом.\n"
        "Сейчас проверяем стабильный запуск 😉"
    )


# =========================
# STARTUP
# =========================

async def on_startup(dp):
    await init_db()
    print("✅ Bot started and DB initialized")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
