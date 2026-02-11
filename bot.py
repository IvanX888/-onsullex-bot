import os
import logging
import json
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

# ============ НАСТРОЙКА ЛОГИРОВАНИЯ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
# ⚠️ ВАЖНО: ADMIN_ID должен быть числом, без кавычек в переменной окружения!
# Например: 717849646 (а не "717849646")
ADMIN_ID_STR = os.getenv("ADMIN_ID", "717849646")
try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    logger.error(f"❌ ADMIN_ID '{ADMIN_ID_STR}' не является числом!")
    ADMIN_ID = 717849646  # Fallback

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

logger.info(f"🔧 ADMIN_ID настроен: {ADMIN_ID} (тип: {type(ADMIN_ID)})")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL не установлен!")

# ============ FSM СОСТОЯНИЯ ============
class ChatState(StatesGroup):
    automatic = State()
    waiting_operator = State()
    operator_active = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# Хранилище активных чатов
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
            [KeyboardButton(text="❌ Завершить разговор с юристом")],
            [KeyboardButton(text="📞 Телефон для связи")]
        ],
        resize_keyboard=True
    )

def admin_reply_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_to:{user_id}")]
    ])

# ============ СИСТЕМА ПРОВЕРКИ ДОСТУПА ============
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    # Логируем для отладки
    logger.info(f"🔍 Проверка доступа: user_id={user_id} (тип: {type(user_id)}), ADMIN_ID={ADMIN_ID} (тип: {type(ADMIN_ID)})")
    result = user_id == ADMIN_ID
    logger.info(f"🔍 Результат проверки: {result}")
    return result

# ============ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    logger.info(f"🚀 /start от пользователя {message.from_user.id} ({message.from_user.full_name})")
    await state.set_state(ChatState.automatic)
    
    welcome_text = f"""
👑 <b>Добро пожаловать в Консуллекс!</b>

Здравствуйте, {message.from_user.first_name}!

Я — личный помощник <b>Ивана Серко</b>, частного юриста премиум-класса.

<b>Ваш ID:</b> <code>{message.from_user.id}</code>
    """
    await message.answer(welcome_text, reply_markup=main_menu())
    
    # Если это админ — показываем дополнительную инфу
    if is_admin(message.from_user.id):
        await message.answer(
            "🔐 <b>Вы администратор бота!</b>\n"
            "Доступные команды:\n"
            "/chats — список активных чатов\n"
            "/reply ID — ответить пользователю"
        )

@dp.message(Command("id"))
async def cmd_id(message: types.Message):
    """Показать свой ID"""
    await message.answer(f"🆔 <b>Ваш ID:</b> <code>{message.from_user.id}</code>")

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    logger.info(f"🏓 Ping от {message.from_user.id}")
    await message.answer("🏓 Pong! Бот работает.")

# ============ МЕНЮ ============
@dp.message(F.text == "📝 Оставить заявку")
async def start_request(message: types.Message):
    await message.answer("📞 Заявка принята! Свяжемся с вами.")

@dp.message(F.text == "⚖️ Услуги")
async def show_services(message: types.Message):
    await message.answer("⚖️ Услуги: недвижимость, семейные дела, наследство...")

@dp.message(F.text == "💰 Цены")
async def show_prices(message: types.Message):
    await message.answer("💰 Цены от 3 000 ₽")

@dp.message(F.text == "📞 Контакты")
async def show_contacts(message: types.Message):
    await message.answer("📞 +7 (977) 42-32-473")

@dp.message(F.text == "📋 Документы")
async def show_documents(message: types.Message):
    await message.answer("📋 Документы по запросу")

@dp.message(F.text == "❓ FAQ")
async def show_faq(message: types.Message):
    await message.answer("❓ Частые вопросы...")

@dp.message(F.text == "⭐ Отзывы")
async def show_reviews(message: types.Message):
    await message.answer("⭐ Отличные отзывы!")

# ============ СИСТЕМА ОПЕРАТОРА ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
@dp.message(Command("operator"))
async def call_operator(message: types.Message, state: FSMContext):
    """Пользователь запрашивает связь с юристом"""
    logger.info(f"👨‍⚖️ Запрос оператора от {message.from_user.id}")
    
    await state.set_state(ChatState.waiting_operator)
    
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "Ваш вопрос будет передан Ивану Серко.\n"
        "Опишите ситуацию подробно.",
        reply_markup=operator_menu()
    )
    
    # Отправляем уведомление админу
    user = message.from_user
    notification = (
        f"🔔 <b>Новый запрос!</b>\n\n"
        f"👤 <b>{user.full_name}</b>\n"
        f"🆔 <code>{user.id}</code>\n"
        f"📱 @{user.username or 'нет'}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    try:
        admin_msg = await bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            reply_markup=admin_reply_keyboard(user.id)
        )
        active_chats[user.id] = {
            'admin_msg_id': admin_msg.message_id,
            'username': user.username,
            'full_name': user.full_name
        }
        logger.info(f"✅ Уведомление отправлено админу (ID: {ADMIN_ID})")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки админу: {e}")
        logger.error(f"Проверьте: ADMIN_ID={ADMIN_ID}, тип={type(ADMIN_ID)}")
        await message.answer(
            "⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473"
        )

@dp.message(F.text == "❌ Завершить разговор с юристом")
@dp.message(Command("stop"))
async def end_operator_chat(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    logger.info(f"🛑 Завершение чата от {message.from_user.id}, состояние: {current_state}")
    
    if current_state in [ChatState.waiting_operator.state, ChatState.operator_active.state]:
        user_id = message.from_user.id
        
        if user_id in active_chats:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Клиент {active_chats[user_id]['full_name']} завершил разговор."
                )
                del active_chats[user_id]
            except Exception as e:
                logger.error(f"Ошибка уведомления админа: {e}")
        
        await state.set_state(ChatState.automatic)
        await message.answer("✅ Разговор завершён.", reply_markup=main_menu())
    else:
        await message.answer("Вы не в режиме разговора.")

@dp.message(F.text == "📞 Телефон для связи")
async def operator_phone(message: types.Message):
    await message.answer("📞 +7 (977) 42-32-473")

# ============ ПЕРЕСЫЛКА СООБЩЕНИЙ ОПЕРАТОРУ ============
@dp.message(ChatState.waiting_operator)
@dp.message(ChatState.operator_active)
async def message_to_operator(message: types.Message, state: FSMContext):
    """Пересылка сообщений пользователя админу"""
    user_id = message.from_user.id
    user = message.from_user
    
    logger.info(f"📨 Сообщение от {user_id} к оператору")
    
    header = f"💬 <b>{user.full_name}</b> (ID: <code>{user_id}</code>)\n"
    if user.username:
        header += f"@{user.username}\n"
    header += f"⏰ {datetime.now().strftime('%H:%M:%S')}\n—\n\n"
    
    try:
        if message.text:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=header + message.text,
                reply_markup=admin_reply_keyboard(user_id)
            )
        elif message.document:
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=message.document.file_id,
                caption=(header + (message.caption or "📄 Документ"))[:1024],
                reply_markup=admin_reply_keyboard(user_id)
            )
        elif message.photo:
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo[-1].file_id,
                caption=(header + (message.caption or "🖼️ Фото"))[:1024],
                reply_markup=admin_reply_keyboard(user_id)
            )
        elif message.voice:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=header + "🎤 Голосовое:",
                reply_markup=admin_reply_keyboard(user_id)
            )
            await bot.send_voice(
                chat_id=ADMIN_ID,
                voice=message.voice.file_id
            )
        
        current_state = await state.get_state()
        if current_state == ChatState.waiting_operator.state:
            await state.set_state(ChatState.operator_active)
            await message.answer("✅ <b>Отправлено юристу!</b> Ожидайте ответа...")
            
        logger.info(f"✅ Сообщение переслано админу {ADMIN_ID}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка пересылки: {e}")
        await message.answer("⚠️ Ошибка отправки. Позвоните: +7 (977) 42-32-473")

# ============ АДМИН-ПАНЕЛЬ ============
@dp.callback_query(F.data.startswith("reply_to:"))
async def admin_start_reply(callback: CallbackQuery, state: FSMContext):
    """Админ нажал кнопку ответить"""
    user_id = callback.from_user.id
    logger.info(f"🔘 Callback от {user_id}: {callback.data}")
    
    if not is_admin(user_id):
        logger.warning(f"⛔ Доступ запрещён для {user_id}")
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    target_user_id = int(callback.data.split(":")[1])
    
    await state.update_data(replying_to=target_user_id)
    await state.set_state("admin_replying")
    
    await callback.message.answer(
        f"✍️ <b>Режим ответа</b>\n"
        f"Клиент ID: <code>{target_user_id}</code>\n\n"
        f"Отправьте сообщение. /cancel — отмена"
    )
    await callback.answer()

@dp.message(Command("cancel"), State("admin_replying"))
async def admin_cancel_reply(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("❌ Ответ отменён.")

@dp.message(State("admin_replying"))
async def admin_send_reply(message: types.Message, state: FSMContext):
    """Админ отправляет ответ пользователю"""
    if not is_admin(message.from_user.id):
        logger.warning(f"⛔ Попытка отправки от не-админа {message.from_user.id}")
        return
    
    data = await state.get_data()
    user_id = data.get('replying_to')
    
    if not user_id:
        await message.answer("❌ Ошибка: клиент не найден")
        await state.clear()
        return
    
    logger.info(f"📤 Админ отвечает пользователю {user_id}")
    
    try:
        header = "👨‍⚖️ <b>Иван Серко (юрист):</b>\n\n"
        
        if message.text:
            await bot.send_message(chat_id=user_id, text=header + message.text)
        elif message.document:
            await bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=header + (message.caption or "")
            )
        elif message.photo:
            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=header + (message.caption or "")
            )
        elif message.voice:
            await bot.send_voice(chat_id=user_id, voice=message.voice.file_id, caption=header)
        else:
            await message.answer("❌ Тип не поддерживается")
            return
        
        await message.answer(f"✅ Отправлено клиенту {user_id}")
        logger.info(f"✅ Ответ доставлен пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки пользователю: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("chats"))
async def admin_show_chats(message: types.Message):
    """Показать активные чаты"""
    if not is_admin(message.from_user.id):
        return
    
    if not active_chats:
        await message.answer("📭 Нет активных чатов")
        return
    
    text = "📋 <b>Активные чаты:</b>\n\n"
    for uid, info in active_chats.items():
        text += f"• <b>{info['full_name']}</b> (ID: <code>{uid}</code>)\n"
        if info['username']:
            text += f"  @{info['username']}\n"
        text += "\n"
    
    await message.answer(text)

# ============ ОБРАБОТКА ОШИБОК ============
@dp.errors()
async def error_handler(update: types.Update, exception: Exception):
    logger.error(f"❌ Ошибка при обработке {update}: {exception}")
    return True

# ============ WEBHOOK ============
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return web.Response(status=500, text="Error")

async def on_startup(app: web.Application = None):
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")
    logger.info(f"✅ ADMIN_ID: {ADMIN_ID}")
    
    me = await bot.get_me()
    logger.info(f"🤖 Бот @{me.username}")

async def on_shutdown(app: web.Application = None):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("👋 Бот остановлен")

# ============ ВЕБ-СЕРВЕР ============
async def handle_root(request: web.Request):
    return web.Response(
        text=f"✅ Бот работает!\nADMIN_ID: {ADMIN_ID}\n"
    )

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
