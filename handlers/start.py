
from aiogram import Router
from aiogram.types import Message
from database import get_db

router = Router()

@router.message(commands=["start"])
async def start_cmd(message: Message):
    db = await get_db()
    await db.execute("""
        INSERT INTO users (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO NOTHING
    """, message.from_user.id, message.from_user.username)
    await db.close()

    await message.answer(
        "👋 Привет!\n\n"
        "Я бот для трекинга привычек.\n\n"
        "Команды:\n"
        "/add Название\n"
        "/list\n"
        "/done ID\n"
        "/ai — AI-анализ"
    )
