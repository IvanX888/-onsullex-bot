import os
import logging
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
    menu = State()
    talking_to_lawyer = State()

class AdminState(StatesGroup):
    idle = State()
    talking_to_client = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)
active_chats = {}

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

# ============ ОБРАБОТЧИКИ ============

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    
    if uid in active_chats:
        del active_chats[uid]
    
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
        reply_markup=client_main_menu()
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
    
    if uid in active_chats:
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
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>НОВЫЙ КЛИЕНТ!</b>\n\n"
            f"👤 {user.full_name}\n🆔 <code>{uid}</code>\n📱 @{user.username or 'нет'}\n⏰ {datetime.now().strftime('%H:%M')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"start_chat:{uid}:{user.full_name}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        active_chats[uid] = ADMIN_ID
        logger.info(f"✅ Клиент {uid} подключён")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.answer("⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "❌ Завершить разговор с юристом")
async def client_end_chat(message: Message, state: FSMContext):
    uid = message.from_user.id
    if uid in active_chats:
        await end_chat_for_admin(active_chats[uid], dp.fsm.get_context(bot, ADMIN_ID, ADMIN_ID), "Клиент завершил")
    await end_chat_for_client(uid, "Разговор завершён")

@dp.message(StateFilter(ClientState.talking_to_lawyer))
async def client_to_lawyer(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user
    
    if uid not in active_chats:
        await message.answer("⚠️ Связь потеряна", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)
        return
    
    try:
        if message.text:
            await bot.send_message(ADMIN_ID, f"💬 <b>{user.full_name}</b>\n—\n{message.text}", parse_mode=ParseMode.HTML)
        elif message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💬 {user.full_name}")
        elif message.document:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=f"💬 {user.full_name}")
        elif message.voice:
            await bot.send_message(ADMIN_ID, f"💬 <b>{user.full_name}</b>\n—\n🎤 Голосовое:")
            await bot.send_voice(ADMIN_ID, message.voice.file_id)
        
        data = await state.get_data()
        if not data.get('notified'):
            await state.update_data(notified=True)
            await message.reply("✅ Отправлено юристу")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

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
async def admin_start_chat(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    client_id = int(parts[1])
    client_name = parts[2] if len(parts) > 2 else "Клиент"
    
    await state.set_state(AdminState.talking_to_client)
    await state.update_data(talking_to=client_id, client_name=client_name)
    active_chats[client_id] = callback.from_user.id
    
    await callback.message.answer(
        f"✍️ Общение с <b>{client_name}</b>\nID: <code>{client_id}</code>",
        reply_markup=admin_in_chat_menu(client_name),
        parse_mode=ParseMode.HTML
    )
    
    try:
        await bot.send_message(client_id, "👨‍⚖️ <b>Юрист подключился!</b>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Не удалось уведомить: {e}")
    
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
    
    if not client_id or client_id not in active_chats:
        await message.answer("⚠️ Клиент отключился")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return
    
    try:
        header = "👨‍⚖️ <b>Иван Серко:</b>\n\n"
        if message.text:
            await bot.send_message(client_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            await bot.send_photo(client_id, message.photo[-1].file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.document:
            await bot.send_document(client_id, message.document.file_id, caption=header + (message.caption or ""), parse_mode=ParseMode.HTML)
        elif message.voice:
            await bot.send_voice(client_id, message.voice.file_id, caption=header, parse_mode=ParseMode.HTML)
        else:
            await message.answer("❌ Неподдерживаемый тип")
            return
        await message.answer("✅ Отправлено")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.answer(f"❌ Ошибка отправки")

@dp.message(StateFilter(AdminState.idle), F.text == "📊 Статистика")
async def admin_stats_idle(message: Message, state: FSMContext):
    await message.answer(f"📊 Активных: {len(active_chats)}\nСписок: {list(active_chats.keys()) if active_chats else 'нет'}")

@dp.message(StateFilter(AdminState.idle), F.text == "🔄 Перезапустить бота")
async def admin_restart(message: Message, state: FSMContext):
    await cmd_start(message, state)

@dp.message(StateFilter(AdminState.idle))
async def admin_idle(message: Message, state: FSMContext):
    if message.text and message.text.startswith('/'):
        return
    await message.answer("ℹ️ Вы свободны. Ждите клиента или нажмите /start", reply_markup=admin_idle_menu())

# ============ ВСПОМОГАТЕЛЬНЫЕ ============

async def end_chat_for_client(client_id: int, text: str):
    try:
        client_state = dp.fsm.get_context(bot, client_id, client_id)
        await client_state.clear()
        await client_state.set_state(ClientState.menu)
        await bot.send_message(
            client_id,
            f"👨‍⚖️ <b>{text}</b>\n\nНажмите 👨‍⚖️ Связаться с юристом снова",
            reply_markup=client_main_menu(),
            parse_mode=ParseMode.HTML
        )
        if client_id in active_chats:
            del active_chats[client_id]
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        if client_id in active_chats:
            del active_chats[client_id]

async def end_chat_for_admin(admin_id: int, state: FSMContext, text: str):
    try:
        await state.clear()
        await state.set_state(AdminState.idle)
        await bot.send_message(admin_id, f"✅ {text}\n\nВы свободны", reply_markup=admin_idle_menu())
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# ============ WEBHOOK ============

async def handle_webhook(request: web.Request):
    """Обработка входящих обновлений от Telegram"""
    try:
        data = await request.json()
        logger.info(f"📩 Получен webhook: {data.get('update_id', 'unknown')}")
        
        # Используем feed_raw_update
        result = await dp.feed_raw_update(bot, data)
        
        return web.Response(text="OK", status=200)
        
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}", exc_info=True)
        return web.Response(text="Error", status=200)

async def health(request: web.Request):
    return web.Response(text="OK")

async def root(request: web.Request):
    return web.Response(text=f"Bot OK. Admin: {ADMIN_ID}")

async def on_startup(app: web.Application):
    """Устанавливаем webhook при старте"""
    webhook_url = f"{WEBHOOK_URL}/webhook"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")

async def on_shutdown(app: web.Application):
    try:
        await bot.delete_webhook()
        await bot.session.close()
    except Exception as e:
        logger.error(f"❌ Shutdown error: {e}")

# ============ ЗАПУСК ============

def main():
    port = int(os.getenv("PORT", "10000"))
    
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    logger.info(f"🚀 Запуск сервера на порту {port}...")
    
    # Запускаем сервер (блокирует поток, но это нормально)
    web.run_app(
        app,
        host="0.0.0.0",
        port=port,
        access_log=logger,
        print=None
    )

if __name__ == "__main__":
    main()
