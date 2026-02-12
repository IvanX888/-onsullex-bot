import os
import logging
import asyncio
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID}")

# ============ FSM СОСТОЯНИЯ ============
class ClientState(StatesGroup):
    menu = State()
    talking_to_lawyer = State()

class AdminState(StatesGroup):
    idle = State()
    talking_to_client = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# ---------- Защита active_chats ----------
active_chats = {}
active_chats_lock = asyncio.Lock()

async def set_active_chat(client_id: int, admin_id: int):
    async with active_chats_lock:
        active_chats[client_id] = admin_id

async def remove_active_chat(client_id: int):
    async with active_chats_lock:
        active_chats.pop(client_id, None)

async def get_active_chat(client_id: int):
    async with active_chats_lock:
        return active_chats.get(client_id)

# ============ КЛАВИАТУРЫ ============
def client_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку"), KeyboardButton(text="👨‍⚖️ Связаться с юристом")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="❓ Частые вопросы")]
        ],
        resize_keyboard=True
    )

def client_in_chat_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить разговор с юристом")],
            [KeyboardButton(text="📞 Телефон для связи")]
        ],
        resize_keyboard=True
    )

def admin_idle_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔄 Перезапустить бота")]
        ],
        resize_keyboard=True
    )

def admin_in_chat_menu(client_name: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"❌ Завершить диалог с {client_name}")],
            [KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ ГОТОВЫЕ ОТВЕТЫ ============
BOT_ANSWERS = {
    "привет": "👋 Здравствуйте! Я помогу вам с юридическими вопросами.\n\nВыберите действие в меню ниже ⬇️",
    "здравствуйте": "👋 Добрый день! Готов помочь.\n\nВыберите действие в меню ниже ⬇️",
    "цена": "💰 <b>Стоимость консультации:</b>\n\n• Консультация — от 3 000 ₽\n• Документы — от 5 000 ₽\n• Суд — от 15 000 ₽\n\nДля точного расчёта нажмите 👨‍⚖️ <b>Связаться с юристом</b>",
    "стоимость": "💰 Консультация от 3 000 ₽. Свяжитесь с юристом для расчёта.",
    "услуги": "⚖️ <b>Наши услуги:</b>\n\n🏠 <b>Недвижимость</b>\n• Проверка документов\n• Сопровождение сделок\n\n👨‍👩‍👧 <b>Семейные дела</b>\n• Разводы, алименты\n\n📜 <b>Наследство</b>\n• Оформление, оспаривание\n\n💰 <b>Налоги</b>\n• Споры с ФНС\n\n💼 <b>Трудовые споры</b>",
    "контакты": "📞 <b>Контакты:</b>\n\n📱 +7 (977) 42-32-473\n📧 333742917@mail.ru\n🕐 9:00-21:00\n🏛️ г. Москва",
    "телефон": "📞 +7 (977) 42-32-473",
    "спасибо": "🙏 Пожалуйста! Обращайтесь ещё.",
    "до свидания": "👋 До свидания!",
}

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ FSM ============
def get_fsm_context(user_id: int, chat_id: int = None) -> FSMContext:
    """Корректное получение контекста FSM для пользователя."""
    if chat_id is None:
        chat_id = user_id
    key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=chat_id)
    return FSMContext(storage=dp.storage, key=key)

# ============ ОТПРАВКА С ТАЙМАУТОМ ============
async def safe_send_message(chat_id: int, text: str, **kwargs):
    """Отправляет сообщение с таймаутом 15 секунд."""
    try:
        await asyncio.wait_for(
            bot.send_message(chat_id, text, **kwargs),
            timeout=15.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error(f"Таймаут отправки сообщения для {chat_id}")
        return False
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения для {chat_id}: {e}")
        return False

async def safe_send_photo(chat_id: int, photo, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_photo(chat_id, photo, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки фото для {chat_id}: {e}")
        return False

async def safe_send_document(chat_id: int, document, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_document(chat_id, document, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки документа для {chat_id}: {e}")
        return False

async def safe_send_voice(chat_id: int, voice, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_voice(chat_id, voice, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки голосового для {chat_id}: {e}")
        return False

# ============ ЗАВЕРШЕНИЕ ДИАЛОГА ============
async def end_chat_for_client(client_id: int, text: str):
    """Завершает диалог со стороны клиента или автоматически."""
    await remove_active_chat(client_id)
    
    client_state = get_fsm_context(client_id)
    await client_state.clear()
    await client_state.set_state(ClientState.menu)
    
    await safe_send_message(
        client_id,
        f"👨‍⚖️ <b>{text}</b>\n\nНажмите 👨‍⚖️ Связаться с юристом снова",
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

async def end_chat_for_admin(admin_id: int, state: FSMContext, text: str):
    """Завершает диалог со стороны админа."""
    await state.clear()
    await state.set_state(AdminState.idle)
    await safe_send_message(
        admin_id,
        f"✅ {text}\n\nВы свободны",
        reply_markup=admin_idle_menu(),
        parse_mode=ParseMode.HTML
    )

# ============ ОБРАБОТЧИКИ ============

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    await remove_active_chat(uid)
    
    if is_admin(uid):
        await state.set_state(AdminState.idle)
        await message.answer(
            f"🔐 <b>Админ-панель</b>\n\nВы свободны.\nID: <code>{uid}</code>",
            reply_markup=admin_idle_menu(),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"👑 Админ {uid} запустил бота")
    else:
        await state.set_state(ClientState.menu)
        await message.answer(
            f"👑 <b>Консуллекс</b>\n\nПривет, {message.from_user.first_name}!\n\n"
            f"Я — юридический помощник. Выберите действие:",
            reply_markup=client_main_menu(),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"👤 Клиент {uid} запустил бота")

@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    uid = message.from_user.id
    client_id = None
    async with active_chats_lock:
        for cid, aid in list(active_chats.items()):
            if aid == uid:
                client_id = cid
                break
    
    if client_id:
        await end_chat_for_client(client_id, "Админ завершил диалог")
        await end_chat_for_admin(uid, state, "Диалог завершён")
    else:
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("✅ Сброшено", reply_markup=admin_idle_menu())

# ============ КЛИЕНТ ============

@dp.message(StateFilter(ClientState.menu), F.text == "📝 Оставить заявку")
async def client_request(message: Message, state: FSMContext):
    await message.answer(
        "📞 <b>Заявка:</b>\n\n📱 +7 (977) 42-32-473\n📧 333742917@mail.ru\n⏰ Ответ за 15 мин!",
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "⚖️ Услуги")
async def client_services(message: Message, state: FSMContext):
    await message.answer(BOT_ANSWERS["услуги"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "💰 Цены")
async def client_prices(message: Message, state: FSMContext):
    await message.answer(BOT_ANSWERS["цена"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "📞 Контакты")
async def client_contacts(message: Message, state: FSMContext):
    await message.answer(BOT_ANSWERS["контакты"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "❓ Частые вопросы")
async def client_faq(message: Message, state: FSMContext):
    await message.answer(
        "❓ Задайте вопрос или нажмите 👨‍⚖️ Связаться с юристом",
        reply_markup=client_main_menu()
    )

@dp.message(StateFilter(ClientState.menu), F.text == "👨‍⚖️ Связаться с юристом")
async def client_call_lawyer(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user
    
    existing = await get_active_chat(uid)
    if existing:
        await message.answer("⚠️ Вы уже на связи!")
        return
    
    await state.set_state(ClientState.talking_to_lawyer)
    
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "✅ Иван Серко получил уведомление.\n\n"
        "Опишите ситуацию:",
        reply_markup=client_in_chat_menu(),
        parse_mode=ParseMode.HTML
    )
    
    try:
        await safe_send_message(
            ADMIN_ID,
            f"🔔 <b>НОВЫЙ КЛИЕНТ!</b>\n\n"
            f"👤 {user.full_name}\n🆔 <code>{uid}</code>\n📱 @{user.username or 'нет'}\n⏰ {datetime.now().strftime('%H:%M')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"start_chat:{uid}:{user.full_name}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        await set_active_chat(uid, ADMIN_ID)
        logger.info(f"✅ Клиент {uid} подключён")
    except Exception as e:
        logger.error(f"❌ Ошибка при вызове юриста: {e}")
        await message.answer("⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "❌ Завершить разговор с юристом")
async def client_end_chat(message: Message, state: FSMContext):
    uid = message.from_user.id
    admin_id = await get_active_chat(uid)
    if admin_id:
        admin_state = get_fsm_context(admin_id)
        await end_chat_for_admin(admin_id, admin_state, "Клиент завершил диалог")
    await end_chat_for_client(uid, "Разговор завершён")

@dp.message(StateFilter(ClientState.talking_to_lawyer))
async def client_to_lawyer(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user
    
    admin_id = await get_active_chat(uid)
    if not admin_id:
        await message.answer("⚠️ Связь с юристом потеряна. Начните заново.", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)
        return
    
    sent = False
    try:
        header = f"💬 <b>{user.full_name}</b>\n—\n"
        if message.text:
            sent = await safe_send_message(admin_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            sent = await safe_send_photo(admin_id, message.photo[-1].file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.document:
            sent = await safe_send_document(admin_id, message.document.file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.voice:
            await safe_send_message(admin_id, f"💬 <b>{user.full_name}</b>\n—\n🎤 Голосовое:", parse_mode=ParseMode.HTML)
            sent = await safe_send_voice(admin_id, message.voice.file_id, parse_mode=ParseMode.HTML)
        else:
            await message.reply("❌ Неподдерживаемый тип сообщения")
            return
        
        data = await state.get_data()
        if not data.get('notified'):
            await state.update_data(notified=True)
            if sent:
                await message.reply("✅ Отправлено юристу")
            else:
                await message.reply("⚠️ Не удалось отправить, попробуйте позже")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки клиентом: {e}")
        await message.reply("⚠️ Ошибка отправки")

@dp.message(StateFilter(ClientState.menu))
async def client_bot_chat(message: Message, state: FSMContext):
    text = message.text.lower() if message.text else ""
    answer = None
    for key, resp in BOT_ANSWERS.items():
        if key in text:
            answer = resp
            break
    if not answer:
        answer = "🤔 Нажмите 👨‍⚖️ Связаться с юристом для помощи"
    await message.answer(answer, reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

# ============ АДМИН ============

@dp.callback_query(F.data.startswith("start_chat:"))
async def admin_start_chat(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    current_state = await state.get_state()
    if current_state == AdminState.talking_to_client:
        await callback.answer("⚠️ Вы уже ведёте диалог. Завершите его сначала.", show_alert=True)
        return
    
    parts = callback.data.split(":")
    client_id = int(parts[1])
    client_name = parts[2] if len(parts) > 2 else "Клиент"
    
    existing_admin = await get_active_chat(client_id)
    if existing_admin:
        await callback.answer("⚠️ Клиент уже на связи с другим админом.", show_alert=True)
        return
    
    await state.set_state(AdminState.talking_to_client)
    await state.update_data(talking_to=client_id, client_name=client_name)
    await set_active_chat(client_id, callback.from_user.id)
    
    await callback.message.answer(
        f"✍️ Общение с <b>{client_name}</b>\nID: <code>{client_id}</code>",
        reply_markup=admin_in_chat_menu(client_name),
        parse_mode=ParseMode.HTML
    )
    
    await safe_send_message(client_id, "👨‍⚖️ <b>Юрист подключился!</b>", parse_mode=ParseMode.HTML)
    await callback.answer("✅ Подключены")

@dp.message(StateFilter(AdminState.talking_to_client), F.text.startswith("❌ Завершить диалог с"))
async def admin_end_chat(message: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get('talking_to')
    client_name = data.get('client_name', 'Клиент')
    
    if client_id:
        await end_chat_for_client(client_id, "Юрист завершил консультацию")
        await end_chat_for_admin(message.from_user.id, state, f"Диалог с {client_name} завершён")

@dp.message(StateFilter(AdminState.talking_to_client))
async def admin_to_client(message: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data.get('talking_to')
    
    if not client_id:
        await message.answer("⚠️ Нет активного клиента")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return
    
    if not await get_active_chat(client_id):
        await message.answer("⚠️ Клиент отключился или завершил диалог")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return
    
    header = "👨‍⚖️ <b>Иван Серко:</b>\n\n"
    sent = False
    try:
        if message.text:
            sent = await safe_send_message(client_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            sent = await safe_send_photo(client_id, message.photo[-1].file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.document:
            sent = await safe_send_document(client_id, message.document.file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.voice:
            await safe_send_message(client_id, header, parse_mode=ParseMode.HTML)
            sent = await safe_send_voice(client_id, message.voice.file_id, parse_mode=ParseMode.HTML)
        else:
            await message.answer("❌ Неподдерживаемый тип")
            return
        
        if sent:
            await message.answer("✅ Отправлено")
        else:
            await message.answer("⚠️ Ошибка отправки (возможно, клиент недоступен)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки админом: {e}")
        await message.answer("❌ Ошибка отправки")

@dp.message(StateFilter(AdminState.idle), F.text == "📊 Статистика")
async def admin_stats_idle(message: Message, state: FSMContext):
    async with active_chats_lock:
        count = len(active_chats)
        clients = list(active_chats.keys())
    await message.answer(f"📊 Активных диалогов: {count}\nКлиенты: {clients if clients else 'нет'}")

@dp.message(StateFilter(AdminState.idle), F.text == "🔄 Перезапустить бота")
async def admin_restart(message: Message, state: FSMContext):
    await cmd_start(message, state)

@dp.message(StateFilter(AdminState.idle))
async def admin_idle(message: Message, state: FSMContext):
    if message.text and message.text.startswith('/'):
        return
    await message.answer("ℹ️ Вы свободны. Ждите клиента или нажмите /start", reply_markup=admin_idle_menu())

# ============ WEBHOOK (ИСПРАВЛЕННЫЙ) ============

async def handle_webhook(request: web.Request):
    """Обработка входящих обновлений от Telegram."""
    try:
        data = await request.json()
        update_id = data.get('update_id', 'unknown')
        logger.info(f"📩 Получен webhook: {update_id}")
        
        # ОБРАБАТЫВАЕМ СИНХРОННО, ждём результата!
        # Это важно для правильной работы FSM
        result = await dp.feed_raw_update(bot, data)
        
        logger.info(f"✅ Обработан webhook: {update_id}")
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}", exc_info=True)
        return web.Response(text="Error", status=200)

async def health(request: web.Request):
    return web.Response(text="OK")

async def root(request: web.Request):
    return web.Response(text=f"Bot OK. Admin: {ADMIN_ID}")

# ============ ГЛАВНАЯ ФУНКЦИЯ ============

def main():
    """Главная функция - запускает сервер."""
    port = int(os.getenv("PORT", "10000"))
    
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", handle_webhook)
    
    logger.info(f"🚀 Запуск сервера на порту {port}...")
    
    # Запускаем сервер (блокирует поток)
    web.run_app(
        app,
        host="0.0.0.0",
        port=port,
        access_log=logger,
        print=None
    )

if __name__ == "__main__":
    main()
