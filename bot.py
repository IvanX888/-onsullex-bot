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

# ============ НАСТРОЙКА ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID", "717849646")

# ⚠️ КРИТИЧНО: Преобразуем в число!
try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    logger.error(f"❌ ADMIN_ID '{ADMIN_ID_STR}' не число!")
    ADMIN_ID = 717849646

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID} (тип: {type(ADMIN_ID).__name__})")

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

# ============ ПРОВЕРКА АДМИНА ============
def is_admin(uid: int) -> bool:
    result = uid == ADMIN_ID
    logger.info(f"🔍 Проверка: uid={uid} == ADMIN_ID={ADMIN_ID} -> {result}")
    return result

# ============ ОБРАБОТЧИКИ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"🚀 /start от {message.from_user.id}")
    await state.set_state(ChatState.automatic)
    
    text = f"👑 Добро пожаловать, {message.from_user.first_name}!\n\nВаш ID: <code>{message.from_user.id}</code>"
    await message.answer(text, reply_markup=main_menu())
    
    if is_admin(message.from_user.id):
        await message.answer("🔐 Вы АДМИНИСТРАТОР\nКоманды: /chats /id")

@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>")

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong!")

# ============ МЕНЮ (все кнопки) ============
@dp.message(F.text.in_(["📝 Оставить заявку", "📞 Контакты", "📋 Документы", "❓ FAQ", "⭐ Отзывы"]))
async def menu_simple(message: Message):
    responses = {
        "📝 Оставить заявку": "📞 Звоните: +7 (977) 42-32-473",
        "📞 Контакты": "📞 +7 (977) 42-32-473\n📧 333742917@mail.ru",
        "📋 Документы": "📋 Документы по запросу",
        "❓ FAQ": "❓ Частые вопросы...",
        "⭐ Отзывы": "⭐ Отличные отзывы!"
    }
    await message.answer(responses.get(message.text, "Выберите из меню"))

@dp.message(F.text.in_(["⚖️ Услуги", "💰 Цены"]))
async def menu_detailed(message: Message):
    if message.text == "⚖️ Услуги":
        await message.answer("⚖️ Недвижимость, семейные дела, наследство...")
    else:
        await message.answer("💰 От 3 000 ₽")

# ============ СИСТЕМА ОПЕРАТОРА ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
async def call_operator(message: Message, state: FSMContext):
    logger.info(f"👨‍⚖️ Запрос от {message.from_user.id}")
    await state.set_state(ChatState.operator_active)
    
    await message.answer(
        "⏳ Передаю сообщение юристу...\nОпишите ситуацию:",
        reply_markup=operator_menu()
    )
    
    # Уведомление админу
    user = message.from_user
    notif = f"🔔 Новый запрос!\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n📱 @{user.username or 'нет'}"
    
    try:
        await bot.send_message(ADMIN_ID, notif, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{user.id}")]
        ]))
        active_chats[user.id] = {"name": user.full_name, "username": user.username}
        logger.info(f"✅ Уведомлен админ {ADMIN_ID}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки админу: {e}")
        await message.answer("⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473")

@dp.message(F.text == "❌ Завершить разговор")
async def end_chat(message: Message, state: FSMContext):
    current = await state.get_state()
    if current == ChatState.operator_active.state:
        uid = message.from_user.id
        if uid in active_chats:
            try:
                await bot.send_message(ADMIN_ID, f"❌ Клиент {active_chats[uid]['name']} вышел")
                del active_chats[uid]
            except: pass
        await state.set_state(ChatState.automatic)
        await message.answer("✅ Завершено", reply_markup=main_menu())
    else:
        await message.answer("Вы не в режиме разговора")

@dp.message(F.text == "📞 Позвонить")
async def show_phone(message: Message):
    await message.answer("📞 +7 (977) 42-32-473")

# ============ ПЕРЕСЫЛКА В АКТИВНОМ РЕЖИМЕ ============
@dp.message(ChatState.operator_active)
async def forward_to_admin(message: Message, state: FSMContext):
    """Всё пересылаем админу"""
    uid = message.from_user.id
    user = message.from_user
    
    header = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n—\n\n"
    
    try:
        if message.text:
            await bot.send_message(ADMIN_ID, header + message.text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
            ]))
        elif message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=header[:1024])
        elif message.document:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=header[:1024])
        elif message.voice:
            await bot.send_message(ADMIN_ID, header + "🎤 Голосовое:")
            await bot.send_voice(ADMIN_ID, message.voice.file_id)
        
        # Подтверждение пользователю только первый раз
        data = await state.get_data()
        if not data.get('sent'):
            await state.update_data(sent=True)
            await message.answer("✅ Отправлено юристу. Ждите ответа...")
            
    except Exception as e:
        logger.error(f"❌ Ошибка пересылки: {e}")
        await message.answer("⚠️ Ошибка. Позвоните: +7 (977) 42-32-473")

# ============ АДМИН: ОТВЕТ ============
@dp.callback_query(F.data.startswith("reply:"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    uid = int(callback.data.split(":")[1])
    await state.update_data(reply_to=uid)
    await state.set_state("admin_replying")
    
    await callback.message.answer(f"✍️ Режим ответа пользователю {uid}\nОтправьте сообщение. /cancel — отмена")
    await callback.answer()

@dp.message(Command("cancel"), State("admin_replying"))
async def admin_cancel(message: Message, state: FSMContext):
    if is_admin(message.from_user.id):
        await state.clear()
        await message.answer("❌ Отменено")

@dp.message(State("admin_replying"))
async def admin_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    uid = data.get('reply_to')
    
    if not uid:
        await message.answer("❌ Ошибка")
        await state.clear()
        return
    
    try:
        header = "👨‍⚖️ <b>Иван Серко:</b>\n\n"
        
        if message.text:
            await bot.send_message(uid, header + message.text)
        elif message.photo:
            await bot.send_photo(uid, message.photo[-1].file_id, caption=header + (message.caption or ""))
        elif message.document:
            await bot.send_document(uid, message.document.file_id, caption=header + (message.caption or ""))
        elif message.voice:
            await bot.send_voice(uid, message.voice.file_id, caption=header)
        
        await message.answer(f"✅ Отправлено {uid}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("chats"))
async def admin_chats(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    if not active_chats:
        await message.answer("📭 Нет активных чатов")
        return
    
    text = "📋 Активные чаты:\n\n"
    for uid, info in active_chats.items():
        text += f"• {info['name']} (ID: <code>{uid}</code>)\n"
    await message.answer(text)

# ============ ВАЖНО: ОБРАБОТКА ЛЮБОГО ТЕКСТА ============
@dp.message(ChatState.automatic)
async def any_text(message: Message):
    """Ловим любой текст в автоматическом режиме"""
    logger.info(f"💬 Текст от {message.from_user.id}: {message.text[:50]}...")
    await message.answer(
        "Я не понял команду. Выберите из меню или нажмите 👨‍⚖️ Связаться с юристом",
        reply_markup=main_menu()
    )

# ============ WEBHOOK ============
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return web.Response(status=500)

async def on_startup(app: web.Application = None):
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")
    me = await bot.get_me()
    logger.info(f"🤖 Бот @{me.username}")

async def on_shutdown(app: web.Application = None):
    await bot.delete_webhook()
    await bot.session.close()

def create_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text=f"✅ Бот работает! ADMIN_ID: {ADMIN_ID}"))
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
