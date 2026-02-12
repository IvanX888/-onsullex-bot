import os
import logging
import asyncio
import threading
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, Update
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

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID}")

# ============ FSM СОСТОЯНИЯ ============
class ClientState(StatesGroup):
    menu = State()           # Главное меню клиента
    talking_to_lawyer = State()  # Общение с юристом

class AdminState(StatesGroup):
    idle = State()           # Админ свободен
    talking_to_client = State()  # Общение с конкретным клиентом

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# Хранилище: client_id -> admin_id (кто с кем общается)
active_chats = {}

# ============ КЛАВИАТУРЫ ============

def client_main_menu():
    """Главное меню клиента"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку"), KeyboardButton(text="👨‍⚖️ Связаться с юристом")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="❓ Частые вопросы")]
        ],
        resize_keyboard=True
    )

def client_in_chat_menu():
    """Меню клиента во время общения с юристом"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить разговор с юристом")],
            [KeyboardButton(text="📞 Телефон для связи")]
        ],
        resize_keyboard=True
    )

def admin_idle_menu():
    """Меню админа когда свободен"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔄 Перезапустить бота")]
        ],
        resize_keyboard=True
    )

def admin_in_chat_menu(client_name: str):
    """Меню админа во время общения с клиентом"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"❌ Завершить диалог с {client_name}")],
            [KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

# ============ ПРОВЕРКА ============
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ ГОТОВЫЕ ОТВЕТЫ БОТА ============
BOT_ANSWERS = {
    "привет": "👋 Здравствуйте! Я помогу вам с юридическими вопросами.\n\nВыберите действие в меню ниже ⬇️",
    "здравствуйте": "👋 Добрый день! Готов помочь.\n\nВыберите действие в меню ниже ⬇️",
    "цена": "💰 <b>Стоимость консультации:</b>\n\n• Консультация — от 3 000 ₽\n• Документы — от 5 000 ₽\n• Суд — от 15 000 ₽\n\nДля точного расчёта нажмите 👨‍⚖️ <b>Связаться с юристом</b>",
    "стоимость": "💰 Консультация от 3 000 ₽. Свяжитесь с юристом для расчёта.",
    "услуги": "⚖️ <b>Наши услуги:</b>\n\n🏠 <b>Недвижимость</b>\n• Проверка документов\n• Сопровождение сделок\n• Споры с застройщиками\n\n👨‍👩‍👧 <b>Семейные дела</b>\n• Разводы и раздел имущества\n• Алименты\n• Опека\n\n📜 <b>Наследство</b>\n• Оформление\n• Оспаривание завещаний\n\n💰 <b>Налоги</b>\n• Споры с ФНС\n• Возврат налогов\n\n💼 <b>Трудовые споры</b>\n• Увольнения\n• Долги по зарплате",
    "контакты": "📞 <b>Контакты:</b>\n\n📱 Телефон/WhatsApp:\n+7 (977) 42-32-473\n\n📧 Email:\n333742917@mail.ru\n\n🕐 Режим работы:\n9:00-21:00, ежедневно\n\n🏛️ Адрес:\nг. Москва (офис по договорённости)",
    "телефон": "📞 +7 (977) 42-32-473 (WhatsApp/Telegram)",
    "адрес": "🏛️ г. Москва, офис по договорённости",
    "время": "🕐 Работаем ежедневно 9:00-21:00",
    "спасибо": "🙏 Пожалуйста! Обращайтесь, если будут вопросы.",
    "до свидания": "👋 До свидания! Хорошего дня!",
}

# ============ КОМАНДЫ ============

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка /start для всех"""
    uid = message.from_user.id
    
    # Очищаем все состояния
    await state.clear()
    
    # Удаляем из активных чатов если был
    if uid in active_chats:
        del active_chats[uid]
    
    if is_admin(uid):
        # АДМИН
        await state.set_state(AdminState.idle)
        await message.answer(
            f"🔐 <b>Админ-панель</b>\n\n"
            f"Вы свободны.\n"
            f"Когда клиент нажмёт «Связаться с юристом» — вы получите уведомление.\n\n"
            f"Ваш ID: <code>{uid}</code>",
            reply_markup=admin_idle_menu(),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"👑 Админ {uid} запустил бота")
    else:
        # КЛИЕНТ
        await state.set_state(ClientState.menu)
        await message.answer(
            f"👑 <b>Добро пожаловать в Консуллекс!</b>\n\n"
            f"Здравствуйте, {message.from_user.first_name}!\n\n"
            f"Я — юридический помощник. Выберите нужный раздел в меню ниже.\n\n"
            f"Для связи с юристом нажмите 👨‍⚖️ <b>Связаться с юристом</b>",
            reply_markup=client_main_menu(),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"👤 Клиент {uid} запустил бота")

@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    """Аварийная остановка для админа"""
    if not is_admin(message.from_user.id):
        return
    
    uid = message.from_user.id
    
    # Находим клиента, с которым общаемся
    client_id = None
    for cid, aid in list(active_chats.items()):
        if aid == uid:
            client_id = cid
            break
    
    if client_id:
        # Завершаем диалог с клиентом
        await end_chat_for_client(client_id, "Админ завершил диалог командой /stop")
        await end_chat_for_admin(uid, state, "Диалог завершён командой /stop")
    else:
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("✅ Состояние сброшено. Вы свободны.", reply_markup=admin_idle_menu())

# ============ КЛИЕНТ: МЕНЮ ============

@dp.message(StateFilter(ClientState.menu), F.text == "📝 Оставить заявку")
async def client_request(message: Message, state: FSMContext):
    await message.answer(
        "📞 <b>Оставить заявку:</b>\n\n"
        "📱 WhatsApp/Telegram: +7 (977) 42-32-473\n"
        "📧 Email: 333742917@mail.ru\n\n"
        "⏰ Ответим в течение 15 минут!",
        reply_markup=client_main_menu()
    )

@dp.message(StateFilter(ClientState.menu), F.text == "⚖️ Услуги")
async def client_services(message: Message, state: FSMContext):
    await message.answer(
        BOT_ANSWERS["услуги"],
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "💰 Цены")
async def client_prices(message: Message, state: FSMContext):
    await message.answer(
        BOT_ANSWERS["цена"],
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "📞 Контакты")
async def client_contacts(message: Message, state: FSMContext):
    await message.answer(
        BOT_ANSWERS["контакты"],
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "❓ Частые вопросы")
async def client_faq(message: Message, state: FSMContext):
    await message.answer(
        "❓ <b>Задайте вопрос!</b>\n\n"
        "Напишите любой вопрос, я постараюсь помочь.\n\n"
        "Примеры:\n"
        "• Сколько стоит консультация?\n"
        "• Какие услуги вы оказываете?\n"
        "• Как с вами связаться?\n\n"
        "Или нажмите 👨‍⚖️ <b>Связаться с юристом</b> для личной консультации.",
        reply_markup=client_main_menu()
    )

# ============ КЛИЕНТ: ПЕРЕКЛЮЧЕНИЕ НА ЮРИСТА ============

@dp.message(StateFilter(ClientState.menu), F.text == "👨‍⚖️ Связаться с юристом")
async def client_call_lawyer(message: Message, state: FSMContext):
    """Клиент нажал связаться с юристом"""
    uid = message.from_user.id
    user = message.from_user
    
    # Проверяем, не в чате ли уже
    if uid in active_chats:
        await message.answer("⚠️ Вы уже на связи с юристом!")
        return
    
    # Устанавливаем состояние
    await state.set_state(ClientState.talking_to_lawyer)
    
    # Отправляем клиенту
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "✅ <b>Иван Серко</b> получил уведомление.\n\n"
        "📝 <b>Опишите вашу ситуацию:</b>\n"
        "• В чём проблема?\n"
        "• Когда возникла?\n"
        "• Какие документы есть?\n\n"
        "💡 Можете отправить фото или документы.\n\n"
        "⏳ Ожидайте ответа...",
        reply_markup=client_in_chat_menu(),
        parse_mode=ParseMode.HTML
    )
    
    # Отправляем админу уведомление
    try:
        admin_msg = await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>НОВЫЙ КЛИЕНТ!</b>\n\n"
            f"👤 Имя: {user.full_name}\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📱 @{user.username or 'нет username'}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Клиент ждёт ответа...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить клиенту", callback_data=f"start_chat:{uid}:{user.full_name}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        
        # Сохраняем связь
        active_chats[uid] = ADMIN_ID
        
        logger.info(f"✅ Клиент {uid} подключён к админу")
        
    except Exception as e:
        logger.error(f"❌ Ошибка уведомления админа: {e}")
        await message.answer(
            "⚠️ Ошибка связи. Позвоните напрямую:\n📞 +7 (977) 42-32-473",
            reply_markup=client_main_menu()
        )
        await state.set_state(ClientState.menu)

# ============ КЛИЕНТ: ВО ВРЕМЯ ЧАТА С ЮРИСТОМ ============

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "❌ Завершить разговор с юристом")
async def client_end_chat(message: Message, state: FSMContext):
    """Клиент сам завершает разговор"""
    uid = message.from_user.id
    
    if uid in active_chats:
        admin_id = active_chats[uid]
        await end_chat_for_admin(admin_id, dp.fsm.get_context(bot, admin_id, admin_id), "Клиент завершил диалог")
    
    await end_chat_for_client(uid, "Вы завершили разговор с юристом")

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "📞 Телефон для связи")
async def client_phone_in_chat(message: Message, state: FSMContext):
    await message.answer("📞 +7 (977) 42-32-473 (WhatsApp/Telegram)")

@dp.message(StateFilter(ClientState.talking_to_lawyer))
async def client_to_lawyer_message(message: Message, state: FSMContext):
    """Пересылка сообщений клиента -> юристу"""
    uid = message.from_user.id
    user = message.from_user
    
    if uid not in active_chats:
        await message.answer(
            "⚠️ Связь с юристом потеряна.\nНажмите 👨‍⚖️ Связаться с юристом снова.",
            reply_markup=client_main_menu()
        )
        await state.set_state(ClientState.menu)
        return
    
    admin_id = active_chats[uid]
    
    try:
        # Пересылаем админу
        if message.text:
            await bot.send_message(
                admin_id,
                f"💬 <b>{user.full_name}</b>\n"
                f"—\n{message.text}",
                parse_mode=ParseMode.HTML
            )
        elif message.photo:
            caption = f"💬 <b>{user.full_name}</b>\n—\n" + (message.caption or "🖼️ Фото")
            await bot.send_photo(
                admin_id,
                message.photo[-1].file_id,
                caption=caption[:1024]
            )
        elif message.document:
            caption = f"💬 <b>{user.full_name}</b>\n—\n" + (message.caption or "📄 Документ")
            await bot.send_document(
                admin_id,
                message.document.file_id,
                caption=caption[:1024]
            )
        elif message.voice:
            await bot.send_message(
                admin_id,
                f"💬 <b>{user.full_name}</b>\n—\n🎤 Голосовое сообщение:"
            )
            await bot.send_voice(admin_id, message.voice.file_id)
        else:
            await bot.send_message(admin_id, f"💬 <b>{user.full_name}</b> отправил неподдерживаемый тип сообщения")
        
        # Первое сообщение — подтверждение
        data = await state.get_data()
        if not data.get('notified'):
            await state.update_data(notified=True)
            await message.reply("✅ Сообщение отправлено юристу. Ожидайте ответа...")
            
    except Exception as e:
        logger.error(f"❌ Ошибка пересылки к админу: {e}")
        await message.answer("⚠️ Ошибка отправки. Попробуйте ещё раз.")

# ============ КЛИЕНТ: АВТООТВЕТЫ В МЕНЮ ============

@dp.message(StateFilter(ClientState.menu))
async def client_bot_chat(message: Message, state: FSMContext):
    """Автоответы бота в главном меню"""
    text = message.text.lower() if message.text else ""
    
    # Ищем готовый ответ
    answer = None
    for key, resp in BOT_ANSWERS.items():
        if key in text:
            answer = resp
            break
    
    if not answer:
        answer = "🤔 Чтобы получить точный ответ, рекомендую связаться с юристом — нажмите 👨‍⚖️ <b>Связаться с юристом</b>"
    
    await message.answer(answer, reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

# ============ АДМИН: CALLBACK (НАЖАТИЕ "ОТВЕТИТЬ") ============

@dp.callback_query(F.data.startswith("start_chat:"))
async def admin_start_chat(callback: types.CallbackQuery, state: FSMContext):
    """Админ нажал кнопку Ответить клиенту"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    # Парсим данные: start_chat:client_id:client_name
    parts = callback.data.split(":")
    client_id = int(parts[1])
    client_name = parts[2] if len(parts) > 2 else "Клиент"
    
    # Проверяем, не занят ли клиент
    if client_id in active_chats and active_chats[client_id] != callback.from_user.id:
        await callback.answer("⚠️ Этот клиент уже общается с другим оператором", show_alert=True)
        return
    
    # Устанавливаем состояние админа
    await state.set_state(AdminState.talking_to_client)
    await state.update_data(talking_to=client_id, client_name=client_name)
    
    # Обновляем связь
    active_chats[client_id] = callback.from_user.id
    
    await callback.message.answer(
        f"✍️ <b>Режим общения с клиентом</b>\n\n"
        f"👤 Клиент: <b>{client_name}</b>\n"
        f"🆔 ID: <code>{client_id}</code>\n\n"
        f"Все ваши сообщения сейчас идут этому клиенту.\n"
        f"Нажмите ❌ чтобы завершить диалог.",
        reply_markup=admin_in_chat_menu(client_name),
        parse_mode=ParseMode.HTML
    )
    
    # Уведомляем клиента
    try:
        await bot.send_message(
            client_id,
            "👨‍⚖️ <b>Юрист подключился!</b>\n\n"
            "Можете задавать вопросы.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"❌ Не удалось уведомить клиента {client_id}: {e}")
    
    await callback.answer("✅ Вы подключены к клиенту")

# ============ АДМИН: ВО ВРЕМЯ ЧАТА С КЛИЕНТОМ ============

@dp.message(StateFilter(AdminState.talking_to_client), F.text.startswith("❌ Завершить диалог с"))
async def admin_end_chat_button(message: Message, state: FSMContext):
    """Админ нажал кнопку завершить диалог"""
    data = await state.get_data()
    client_id = data.get('talking_to')
    client_name = data.get('client_name', 'Клиент')
    
    if not client_id:
        await message.answer("❌ Нет активного диалога")
        return
    
    # Завершаем
    await end_chat_for_client(client_id, "Юрист завершил консультацию")
    await end_chat_for_admin(message.from_user.id, state, f"Диалог с {client_name} завершён")

@dp.message(StateFilter(AdminState.talking_to_client), F.text == "📊 Статистика")
async def admin_stats_in_chat(message: Message, state: FSMContext):
    """Статистика во время чата"""
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"🟢 Активных диалогов: {len(active_chats)}\n"
        f"👥 Всего пользователей: {len(set(list(active_chats.keys())))}"
    )

@dp.message(StateFilter(AdminState.talking_to_client))
async def admin_to_client_message(message: Message, state: FSMContext):
    """Пересылка сообщений админа -> клиенту"""
    data = await state.get_data()
    client_id = data.get('talking_to')
    
    if not client_id:
        await message.answer("❌ Ошибка: клиент не найден")
        return
    
    # Проверяем, что клиент всё ещё в активных чатах
    if client_id not in active_chats or active_chats[client_id] != message.from_user.id:
        await message.answer("⚠️ Клиент отключился или диалог завершён")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return
    
    try:
        header = "👨‍⚖️ <b>Иван Серко (юрист):</b>\n\n"
        
        if message.text:
            await bot.send_message(client_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            await bot.send_photo(
                client_id,
                message.photo[-1].file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.document:
            await bot.send_document(
                client_id,
                message.document.file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.voice:
            await bot.send_voice(
                client_id,
                message.voice.file_id,
                caption=header,
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer("❌ Этот тип сообщений не поддерживается")
            return
        
        await message.answer("✅ Отправлено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки клиенту {client_id}: {e}")
        await message.answer(f"❌ Ошибка: клиент заблокировал бота или недоступен")

# ============ АДМИН: В СВОБОДНОМ СОСТОЯНИИ ============

@dp.message(StateFilter(AdminState.idle), F.text == "📊 Статистика")
async def admin_stats_idle(message: Message, state: FSMContext):
    """Статистика когда админ свободен"""
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"🟢 Активных диалогов: {len(active_chats)}\n"
        f"📋 Список активных: {list(active_chats.keys()) if active_chats else 'нет'}"
    )

@dp.message(StateFilter(AdminState.idle), F.text == "🔄 Перезапустить бота")
async def admin_restart(message: Message, state: FSMContext):
    """Перезапуск бота админом"""
    await cmd_start(message, state)

@dp.message(StateFilter(AdminState.idle))
async def admin_idle_message(message: Message, state: FSMContext):
    """Сообщения админа в свободном состоянии"""
    if message.text and message.text.startswith('/'):
        return  # Пропускаем команды
    
    await message.answer(
        "ℹ️ Вы свободны. Дождитесь уведомления о новом клиенте.\n\n"
        "Используйте /start для перезапуска.",
        reply_markup=admin_idle_menu()
    )

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def end_chat_for_client(client_id: int, message_text: str):
    """Завершить чат для клиента"""
    try:
        # Получаем состояние клиента
        client_state = dp.fsm.get_context(bot, client_id, client_id)
        
        # Очищаем и возвращаем в меню
        await client_state.clear()
        await client_state.set_state(ClientState.menu)
        
        # Отправляем сообщение
        await bot.send_message(
            client_id,
            f"👨‍⚖️ <b>{message_text}</b>\n\n"
            f"Если остались вопросы — нажмите 👨‍⚖️ <b>Связаться с юристом</b>",
            reply_markup=client_main_menu(),
            parse_mode=ParseMode.HTML
        )
        
        # Удаляем из активных
        if client_id in active_chats:
            del active_chats[client_id]
            
        logger.info(f"✅ Чат завершён для клиента {client_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка завершения чата клиента {client_id}: {e}")
        if client_id in active_chats:
            del active_chats[client_id]

async def end_chat_for_admin(admin_id: int, state: FSMContext, message_text: str):
    """Завершить чат для админа"""
    try:
        await state.clear()
        await state.set_state(AdminState.idle)
        await state.update_data(talking_to=None, client_name=None)
        
        await bot.send_message(
            admin_id,
            f"✅ <b>{message_text}</b>\n\nВы свободны.",
            reply_markup=admin_idle_menu(),
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"✅ Чат завершён для админа {admin_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка завершения чата админа {admin_id}: {e}")

# ============ WEBHOOK ============

async def handle_webhook(request: web.Request):
    """Обработка входящих обновлений от Telegram"""
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return web.Response(text="Error", status=200)

async def health_check(request: web.Request):
    """Health check для Render"""
    return web.Response(text="OK")

async def root_handler(request: web.Request):
    """Корневой URL"""
    return web.Response(text=f"Bot OK. Admin: {ADMIN_ID}")

# ============ ГЛАВНАЯ ФУНКЦИЯ (ИСПРАВЛЕННАЯ) ============

async def setup_webhook():
    """Установка webhook после запуска сервера"""
    await asyncio.sleep(3)  # Ждём полного запуска сервера
    webhook_url = f"{WEBHOOK_URL}/webhook"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

def run_server():
    """Запуск сервера в отдельном потоке"""
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/health", health_check)
    app.router.add_post("/webhook", handle_webhook)
    
    port = int(os.getenv("PORT", "10000"))
    logger.info(f"🚀 Запуск сервера на порту {port}...")
    
    # Запускаем сервер
    web.run_app(app, host="0.0.0.0", port=port)

async def main():
    """Главная функция"""
    # Запускаем сервер в отдельном потоке, чтобы не блокировать
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Даём серверу время запуститься
    await asyncio.sleep(2)
    
    # Устанавливаем webhook
    await setup_webhook()
    
    # Держим программу живой
    while True:
        await asyncio.sleep(60)  # Проверка каждую минуту
        logger.info("💓 Бот работает...")

if __name__ == "__main__":
    asyncio.run(main())
