import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Update
from aiogram.enums import ParseMode

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL не установлен!")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в <b>Консуллекс</b>!\n\n"
        "Я помогу вам с юридическими консультациями.\n"
        "Используйте /help для списка команд."
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — начать работу\n"
        "/help — помощь\n"
        "/ping — проверить работу бота\n"
        "/admin — панель администратора"
    )

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong! Бот работает исправно.")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if ADMIN_ID and message.from_user.id == int(ADMIN_ID):
        await message.answer("🔐 <b>Админ-панель Консуллекс</b>")
    else:
        await message.answer("⛔ У вас нет доступа к админ-панели.")

# ========== WEBHOOK ==========

async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return web.Response(status=500, text="Ошибка")

async def on_startup(app: web.Application = None):
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")
    me = await bot.get_me()
    logger.info(f"🤖 Бот @{me.username} запущен!")

async def on_shutdown(app: web.Application = None):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("👋 Бот остановлен")

# ========== ВЕБ-СЕРВЕР ==========

async def handle_root(request: web.Request):
    return web.Response(text="✅ Консуллекс бот работает!")

def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)