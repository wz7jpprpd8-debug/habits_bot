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
# START COMMAND
# =========================

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("TEST BUTTON"))

    await message.answer(
        "Если ты видишь кнопку — клавиатура работает",
        reply_markup=kb,
    )

@dp.message_handler()
async def echo(message: types.Message):
    await message.answer(f"Ты нажал: {message.text}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

# =========================
# FALLBACK (чтобы бот не молчал)
# =========================

@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Нажми кнопку «🚀 Открыть приложение» 👇")


# =========================
# RUN
# =========================

if __name__ == "__main__":
    print("BOT_TOKEN =", BOT_TOKEN)
    print("WEBAPP_URL =", WEBAPP_URL)

    executor.start_polling(
        dp,
        skip_updates=True,
    )
