
from aiogram import Router
from aiogram.types import Message
from database import get_db
from utils.analytics import analyze_logs
from utils.prompts import habit_analysis_prompt
from services.llm import ask_ai

router = Router()

@router.message(commands=["ai"])
async def ai_analysis(message: Message):
    db = await get_db()

    habit = await db.fetchrow("""
        SELECT h.id, h.title
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id = $1
        ORDER BY h.created_at
        LIMIT 1
    """, message.from_user.id)

    logs = await db.fetch("""
        SELECT date FROM habit_logs
        WHERE habit_id = $1
        ORDER BY date
    """, habit["id"])

    await db.close()

    stats = analyze_logs([r["date"] for r in logs])
    prompt = habit_analysis_prompt(habit["title"], stats)
    answer = await ask_ai(prompt)

    await message.answer(f"🧠 AI-анализ\n\n{answer}")
