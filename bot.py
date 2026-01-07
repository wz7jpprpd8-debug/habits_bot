import asyncpg
from config import DATABASE_URL


import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import start, habits, ai_analysis

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(habits.router)
dp.include_router(ai_analysis.router)

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)

    with open("models.sql", "r") as f:
        sql = f.read()

    await conn.execute(sql)
    await conn.close()


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
