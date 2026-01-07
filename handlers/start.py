from aiogram import types
from aiogram.dispatcher import Dispatcher
from database import get_db


def register_start(dp: Dispatcher):

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
