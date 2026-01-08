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
    print("START HANDLER CALLED")

    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    keyboard.add(
        KeyboardButton(
            text="🚀 Открыть приложение",
            web_app=WebAppInfo(url=WEBAPP_URL),
        )
    )

    await message.answer(
        "Привет 👋\n\nНажми кнопку ниже, чтобы открыть приложение:",
        reply_markup=keyboard,
    )


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
