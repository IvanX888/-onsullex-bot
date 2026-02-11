import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, Update, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ============ НАСТРОЙКА ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")

logger.info(f"ADMIN_ID: {ADMIN_ID}")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен!")

# ============ FSM ============
class ChatState(StatesGroup):
    automatic = State()
    operator_active = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# ============ МЕНЮ ============
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Заявка"), KeyboardButton(text="👨‍⚖️ Связаться")],
            [KeyboardButton(text="❌ Завершить")]
        ],
        resize_keyboard=True
    )

# ============ ОБРАБОТЧИКИ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ChatState.automatic)
    await message.answer(
        f"Привет! Ваш ID: {message.from_user.id}",
        reply_markup=main_menu()
    )

@dp.message(F.text == "👨‍⚖️ Связаться")
async def call_operator(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Вы админ, это для клиентов")
        return
    
    await state.set_state(ChatState.operator_active)
    await message.answer("Пишите ваш вопрос:", reply_markup=main_menu())
    
    # Уведомление админу
    await bot.send_message(
        ADMIN_ID,
        f"Новый клиент: {message.from_user.full_name} (ID: {message.from_user.id})"
    )

@dp.message(F.text == "❌ Завершить")
async def end_chat(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ChatState.automatic)
    await message.answer("Завершено", reply_markup=main_menu())

@dp.message(ChatState.operator_active)
async def forward_to_admin(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        return
    
    # Пересылаем админу
    await bot.send_message(
        ADMIN_ID,
        f"От {message.from_user.full_name}:\n{message.text}"
    )
    await message.answer("Отправлено юристу")

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
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

# ============ ЗАПУСК ============
app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.router.add_get("/", lambda r: web.Response(text="Bot OK"))
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
