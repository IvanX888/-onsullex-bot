import os
import logging
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")

logger.info(f"ADMIN_ID: {ADMIN_ID}")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ============ МЕНЮ ============
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👨‍⚖️ Связаться с юристом")]
        ],
        resize_keyboard=True
    )

# ============ КЛИЕНТ ============
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Нажмите кнопку ниже:", reply_markup=main_menu())

@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
async def call_operator(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Вы админ, это для клиентов")
        return
    
    await message.answer("✅ Напишите ваш вопрос:")
    # Сохраняем ID клиента
    dp["client_id"] = message.from_user.id
    
    # Уведомление админу
    await bot.send_message(
        ADMIN_ID,
        f"🔔 Новый клиент!\n"
        f"Имя: {message.from_user.full_name}\n"
        f"ID: <code>{message.from_user.id}</code>\n\n"
        f"Чтобы ответить, напишите:\n"
        f"<code>/ответ {message.from_user.id} Ваш текст</code>",
        parse_mode=ParseMode.HTML
    )

@dp.message()
async def client_message(message: Message):
    """Сообщения от клиента к админу"""
    if message.from_user.id == ADMIN_ID:
        return  # Игнорируем сообщения админа здесь
    
    # Пересылаем админу
    await bot.send_message(
        ADMIN_ID,
        f"💬 <b>{message.from_user.full_name}</b> (ID: <code>{message.from_user.id}</code>):\n\n"
        f"{message.text}",
        parse_mode=ParseMode.HTML
    )
    await message.answer("✅ Отправлено юристу")

# ============ АДМИН ============
@dp.message(Command("ответ"))
async def admin_reply(message: Message):
    """Админ отвечает клиенту: /ответ 123456789 Текст ответа"""
    if message.from_user.id != ADMIN_ID:
        return
    
    # Парсим команду
    text = message.text.replace("/ответ", "").strip()
    parts = text.split(" ", 1)
    
    if len(parts) < 2:
        await message.answer("❌ Формат: /ответ ID_клиента Текст\nПример: /ответ 123456789 Привет!")
        return
    
    try:
        client_id = int(parts[0])
        answer_text = parts[1]
    except:
        await message.answer("❌ Неверный ID клиента")
        return
    
    try:
        await bot.send_message(
            client_id,
            f"👨‍⚖️ <b>Иван Серко (юрист):</b>\n\n{answer_text}",
            parse_mode=ParseMode.HTML
        )
        await message.answer(f"✅ Отправлено клиенту {client_id}")
        logger.info(f"Админ ответил клиенту {client_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ============ WEBHOOK ============
async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error: {e}")
        return web.Response(status=500)

async def on_startup(app):
    webhook = f"{WEBHOOK_URL}/webhook"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook)
    logger.info(f"Webhook: {webhook}")

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.router.add_get("/", lambda r: web.Response(text="OK"))
app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
