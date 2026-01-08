import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from aiogram.utils import executor

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not WEBAPP_URL:
    raise RuntimeError("WEBAPP_URL is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# =========================
# START
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.add(
        KeyboardButton(
            "🚀 Открыть приложение",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )
    )

    kb.add(
        KeyboardButton("📋 Мои привычки"),
        KeyboardButton("📊 Статистика"),
    )

    await message.answer(
        "✅ Бот запущен\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=kb,
    )

# =========================
# SIMPLE HANDLERS
# =========================

@dp.message_handler(lambda m: m.text == "📋 Мои привычки")
async def habits_stub(message: types.Message):
    await message.answer("📋 Здесь будут привычки (бот работает)")

@dp.message_handler(lambda m: m.text == "📊 Статистика")
async def stats_stub(message: types.Message):
    await message.answer("📊 Здесь будет статистика")

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Нажми кнопку «🚀 Открыть приложение» 👇")

# =========================
# RUN
# =========================

if __name__ == "__main__":
    print("BOT_TOKEN =", BOT_TOKEN)
    print("WEBAPP_URL =", WEBAPP_URL)
    executor.start_polling(dp, skip_updates=True)
