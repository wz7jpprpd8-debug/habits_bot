    import os
    import asyncio
    import asyncpg
    from datetime import date, timedelta

    from aiogram import Bot, Dispatcher, types
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    from aiogram.utils import executor
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

    from aiohttp import web


    # =========================
    # CONFIG
    # =========================

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")
    WEBAPP_URL = os.getenv("WEBAPP_URL")  # https://your-domain

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(bot)


    # =========================
    # DB
    # =========================

    async def get_db():
        return await asyncpg.connect(DATABASE_URL)


    async def init_db():
        conn = await get_db()
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS habits (
            id SERIAL PRIMARY KEY,
            user_id INT,
            title TEXT,
            streak INT DEFAULT 0,
            last_completed DATE,
            is_active BOOLEAN DEFAULT TRUE
        );

        CREATE TABLE IF NOT EXISTS habit_logs (
            id SERIAL PRIMARY KEY,
            habit_id INT,
            date DATE
        );
        """)
        await conn.close()


    # =========================
    # BOT
    # =========================

    @dp.message_handler(commands=["start"])
    async def start_cmd(message: types.Message):
        db = await get_db()
        await db.execute(
            "INSERT INTO users (telegram_id) VALUES ($1) ON CONFLICT DO NOTHING",
            message.from_user.id,
        )
        await db.close()

       kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        KeyboardButton(
            "🚀 Открыть приложение",
            web_app=WebAppInfo(
                url="https://storied-bubblegum-a94e6a.netlify.app"
            )
        )
    )

    await message.answer(
        "Открой Mini App 👇",
        reply_markup=kb
    )


    # =========================
    # MINI APP API (aiohttp)
    # =========================

    routes = web.RouteTableDef()


    @routes.post("/api/habits")
    async def api_habits(request):
        data = await request.json()
        telegram_id = data.get("telegram_id")

        if not telegram_id:
            return web.json_response([])

        db = await get_db()
        rows = await db.fetch("""
            SELECT h.id, h.title, h.streak
            FROM habits h
            JOIN users u ON h.user_id = u.id
            WHERE u.telegram_id=$1 AND h.is_active=TRUE
            ORDER BY h.id
        """, telegram_id)
        await db.close()

        return web.json_response([
            {"id": r["id"], "title": r["title"], "streak": r["streak"]}
            for r in rows
        ])


    @routes.post("/api/done")
    async def api_done(request):
        data = await request.json()
        habit_id = data["habit_id"]
        today = date.today()

        db = await get_db()

        habit = await db.fetchrow(
            "SELECT streak, last_completed FROM habits WHERE id=$1",
            habit_id
        )

        if habit["last_completed"] == today - timedelta(days=1):
            streak = habit["streak"] + 1
        else:
            streak = 1

        await db.execute(
            "UPDATE habits SET streak=$1, last_completed=$2 WHERE id=$3",
            streak, today, habit_id
        )

        await db.execute(
            "INSERT INTO habit_logs (habit_id, date) VALUES ($1, $2)",
            habit_id, today
        )

        await db.close()
        return web.json_response({"ok": True})


    @routes.post("/api/delete")
    async def api_delete(request):
        data = await request.json()
        habit_id = data["habit_id"]

        db = await get_db()
        await db.execute(
            "UPDATE habits SET is_active=FALSE WHERE id=$1",
            habit_id
        )
        await db.close()

        return web.json_response({"ok": True})


    # =========================
    # SERVER START
    # =========================

    async def start_web():
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()

        port = int(os.getenv("PORT", 8000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        print(f"🌐 Web API started on port {port}")


    async def on_startup(_):
        await init_db()
        asyncio.create_task(start_web())
        print("✅ Bot + Mini App backend started")


    if __name__ == "__main__":
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
