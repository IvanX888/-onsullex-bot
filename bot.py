import os
import logging
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, Update
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID}")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

# ============ FSM ============
class ChatState(StatesGroup):
    automatic = State()
    operator_active = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)
active_chats = {}

# ============ КЛАВИАТУРЫ ============
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку"), KeyboardButton(text="👨‍⚖️ Связаться с юристом")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="📋 Документы")],
            [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="⭐ Отзывы")]
        ],
        resize_keyboard=True
    )

def operator_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить разговор")],
            [KeyboardButton(text="📞 Позвонить")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    """Меню для админа (без кнопки связи с юристом)"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="📋 Документы")],
            [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="⭐ Отзывы")],
            [KeyboardButton(text="📊 Статистика")]  # Дополнительно для админа
        ],
        resize_keyboard=True
    )

# ============ ПРОВЕРКА ============
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    logger.info(f"🚀 /start от {uid}")
    
    # Полный сброс состояния
    await state.clear()
    await state.set_state(ChatState.automatic)
    
    # Выбираем меню в зависимости от роли
    if is_admin(uid):
        menu = admin_menu()
        text = f"🔐 <b>Админ-панель</b>\n\nВаш ID: <code>{uid}</code>\n\nВы администратор бота."
        await message.answer(text, reply_markup=menu, parse_mode=ParseMode.HTML)
        await message.answer(
            "⚠️ <b>Важно:</b> Не нажимайте «Связаться с юристом» — это для клиентов!\n"
            "Если случайно нажали — напишите /reset"
        )
    else:
        menu = main_menu()
        text = f"👑 Добро пожаловать, {message.from_user.first_name}!\n\nВаш ID: <code>{uid}</code>"
       
