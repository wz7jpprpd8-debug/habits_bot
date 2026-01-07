from aiogram import types
from aiogram.dispatcher import Dispatcher
from database import get_db

ALTER TABLE habits ADD COLUMN IF NOT EXISTS streak INT DEFAULT 0;
ALTER TABLE habits ADD COLUMN IF NOT EXISTS last_completed DATE;

def register_habits(dp: Dispatcher):

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
            user["id"], title
        )
        await db.close()

        await message.answer(f"✅ Привычка «{title}» добавлена")
