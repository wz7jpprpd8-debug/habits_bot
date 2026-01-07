from aiogram import Router
from aiogram.types import Message
from database import get_db

router = Router()

@router.message(commands=["stats"])
async def stats(message: Message):
    db = await get_db()
    rows = await db.fetch("""
        SELECT h.title, COUNT(l.id) AS days
        FROM habits h
        LEFT JOIN habit_logs l ON h.id = l.habit_id
        WHERE h.user_id=$1
        GROUP BY h.title
    """, message.from_user.id)
    await db.close()

    if not rows:
        await message.answer("Нет данных для статистики")
        return

    text = "📊 Статистика:\n\n"
    for r in rows:
        text += f"• {r['title']}: {r['days']} дней\n"

    await message.answer(text)
