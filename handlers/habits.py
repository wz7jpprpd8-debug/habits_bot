from aiogram import Router
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile
)
from datetime import date, timedelta
from database import get_db
from keyboards import habit_keyboard
from utils.charts import habit_progress_chart
from utils.analytics import analyze_logs
from utils.prompts import habit_analysis_prompt
from services.llm import ask_ai
import os

router = Router()


# -------------------------
# /add — добавить привычку
# -------------------------
@router.message(commands=["add"])
async def add_habit(message: Message):
    title = message.text.replace("/add", "").strip()
    if not title:
        await message.answer("❗ Используй: /add Название привычки")
        return

    db = await get_db()

    user_id = await db.fetchval(
        "SELECT id FROM users WHERE telegram_id = $1",
        message.from_user.id
    )

    if not user_id:
        await message.answer("❌ Пользователь не найден. Напиши /start")
        await db.close()
        return

    await db.execute(
        "INSERT INTO habits (user_id, title) VALUES ($1, $2)",
        user_id, title
    )
    await db.close()

    await message.answer(f"✅ Привычка «{title}» добавлена")


# -------------------------
# /list — список привычек + кнопки
# -------------------------
@router.message(commands=["list"])
async def list_habits(message: Message):
    db = await get_db()

    rows = await db.fetch("""
        SELECT h.id, h.title
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE u.telegram_id = $1
          AND h.is_active = TRUE
        ORDER BY h.created_at
    """, message.from_user.id)

    await db.close()

    if not rows:
        await message.answer("У тебя пока нет привычек")
        return

    for r in rows:
        await message.answer(
            f"📌 <b>{r['title']}</b>",
            reply_markup=habit_keyboard(r["id"]),
            parse_mode="HTML"
        )

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

    if not habit:
        await message.answer("Нет привычек для анализа")
        await db.close()
        return

    logs = await db.fetch("""
        SELECT date FROM habit_logs
        WHERE habit_id = $1
    """, habit["id"])

    await db.close()

    stats = analyze_logs([r["date"] for r in logs])
    if not stats:
        await message.answer("Недостаточно данных для анализа")
        return

    prompt = habit_analysis_prompt(habit["title"], stats)
    answer = await ask_ai(prompt)

    await message.answer(
        f"🧠 <b>AI-анализ привычки</b>\n\n{answer}",
        parse_mode="HTML"
    )


# -------------------------
# /done ID — отметить выполнение
# -------------------------
@router.message(commands=["done"])
async def mark_done(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❗ Используй: /done ID")
        return

    habit_id = int(args[1])
    today = date.today()

    db = await get_db()

    habit = await db.fetchrow("""
        SELECT h.streak, h.last_completed
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE h.id = $1
          AND u.telegram_id = $2
    """, habit_id, message.from_user.id)

    if not habit:
        await message.answer("❌ Привычка не найдена")
        await db.close()
        return

    if habit["last_completed"] == today:
        await message.answer("⚠️ Сегодня уже отмечено")
        await db.close()
        return

    if habit["last_completed"] == today - timedelta(days=1):
        new_streak = habit["streak"] + 1
    else:
        new_streak = 1

    await db.execute("""
        UPDATE habits
        SET streak = $1,
            last_completed = $2
        WHERE id = $3
    """, new_streak, today, habit_id)

    await db.execute("""
        INSERT INTO habit_logs (habit_id, date, completed)
        VALUES ($1, $2, TRUE)
        ON CONFLICT DO NOTHING
    """, habit_id, today)

    await db.close()

    await message.answer(f"🔥 Отлично! Streak: {new_streak} дней")


# -------------------------
# callback done:ID — кнопка "Выполнено"
# -------------------------
@router.callback_query(lambda c: c.data.startswith("done:"))
async def done_callback(callback: CallbackQuery):
    habit_id = int(callback.data.split(":")[1])
    today = date.today()

    db = await get_db()

    habit = await db.fetchrow("""
        SELECT h.streak, h.last_completed
        FROM habits h
        JOIN users u ON h.user_id = u.id
        WHERE h.id = $1
          AND u.telegram_id = $2
    """, habit_id, callback.from_user.id)

    if not habit:
        await callback.answer("❌ Не найдено", show_alert=True)
        await db.close()
        return

    if habit["last_completed"] == today:
        await callback.answer("⚠️ Уже отмечено сегодня", show_alert=True)
        await db.close()
        return

    if habit["last_completed"] == today - timedelta(days=1):
        new_streak = habit["streak"] + 1
    else:
        new_streak = 1

    await db.execute("""
        UPDATE habits
        SET streak = $1,
            last_completed = $2
        WHERE id = $3
    """, new_streak, today, habit_id)

    await db.execute("""
        INSERT INTO habit_logs (habit_id, date, completed)
        VALUES ($1, $2, TRUE)
        ON CONFLICT DO NOTHING
    """, habit_id, today)

    await db.close()

    await callback.answer("🔥 Отмечено!")


# -------------------------
# callback stats:ID — статистика + график
# -------------------------
@router.callback_query(lambda c:
