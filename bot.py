import asyncio
import asyncpg

from aiogram import Bot, Dispatcher
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(habits.router)
dp.include_router(ai_analysis.router)


# -------------------------
# ИНИЦИАЛИЗАЦИЯ БД (Render, вариант A)
# -------------------------
async def init_db():
    """
    Выполняет models.sql при старте.
    Безопасно за счёт CREATE TABLE IF NOT EXISTS
    """
    conn = await asyncpg.connect(DATABASE_URL)

    with open("models.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    await conn.execute(sql)
    await conn.close()


# -------------------------
# MAIN
# -------------------------
async def main():
    # 1️⃣ создаём таблицы (один раз / безопасно)
    await init_db()

    # 2️⃣ запускаем бота
    await dp.start_polling(bot)


# -------------------------
# ENTRYPOINT
# -------------------------
if __name__ == "__main__":
    asyncio.run(main())
