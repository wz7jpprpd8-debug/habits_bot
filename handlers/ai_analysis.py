from aiogram import types
from aiogram.dispatcher import Dispatcher


def register_ai(dp: Dispatcher):

    @dp.message_handler(commands=["ai"])
    async def ai_stub(message: types.Message):
        await message.answer("🧠 AI-анализ скоро будет 😉")
