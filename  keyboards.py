from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def habit_keyboard(habit_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"done:{habit_id}")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data=f"stats:{habit_id}")]
        ]
    )
