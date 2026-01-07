import asyncio
import asyncpg

from aiogram import Bot, Dispatcher
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor

from config import BOT_TOKEN, DATABASE_URL
import handlers.start
import handlers.habits
import handlers.ai_analysis


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())


async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    with open("models.sql", "r", encoding="utf-8") as f:
        await conn.execute(f.read())
    await conn.close()


async def on_startup(dp):
    await init_db()
    print("✅ Bot started")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
