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

# ============ ПРОВЕРКА АДМИНА ============
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ ОБРАБОТЧИКИ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    logger.info(f"🚀 /start от {message.from_user.id}")
    await state.set_state(ChatState.automatic)
    await state.clear()  # Полная очистка состояния
    
    text = f"👑 Добро пожаловать, {message.from_user.first_name}!\n\nВаш ID: <code>{message.from_user.id}</code>"
    
    # Удаляем старую клавиатуру и показываем новую
    await message.answer(
        text, 
        reply_markup=main_menu(),
        parse_mode=ParseMode.HTML
    )
    
    if is_admin(message.from_user.id):
        await message.answer(
            "🔐 Вы АДМИНИСТРАТОР\n\n"
            "Команды:\n"
            "/id — ваш ID\n"
            "/chats — активные чаты\n"
            "/stop — выйти из режима оператора"
        )

@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>")

@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    """Выход из режима оператора"""
    current = await state.get_state()
    logger.info(f"🛑 /stop от {message.from_user.id}, состояние: {current}")
    
    uid = message.from_user.id
    
    # Удаляем из активных чатов
    if uid in active_chats:
        del active_chats[uid]
    
    # Сбрасываем состояние
    await state.clear()
    await state.set_state(ChatState.automatic)
    
    await message.answer(
        "✅ Режим оператора завершён.\nВы вернулись в главное меню.",
        reply_markup=main_menu()
    )

# ============ МЕНЮ ============
@dp.message(F.text.in_(["📝 Оставить заявку", "📞 Контакты", "📋 Документы", "❓ FAQ", "⭐ Отзывы"]))
async def menu_simple(message: Message):
    responses = {
        "📝 Оставить заявку": "📞 Звоните: +7 (977) 42-32-473\n📧 333742917@mail.ru",
        "📞 Контакты": "📞 +7 (977) 42-32-473\n📧 333742917@mail.ru\n🕐 9:00-21:00",
        "📋 Документы": "📋 Документы по запросу у юриста",
        "❓ FAQ": "❓ Частые вопросы:\n• Юрист vs Адвокат\n• Представительство в суде\n• Гарантии возврата",
        "⭐ Отзывы": "⭐ Отзывы клиентов:\n★★★★★ Анна: «Помог с квартирой!»\n★★★★★ Дмитрий: «Развод без проблем»"
    }
    await message.answer(responses.get(message.text, "Выберите из меню"))

@dp.message(F.text.in_(["⚖️ Услуги", "💰 Цены"]))
async def menu_detailed(message: Message):
    if message.text == "⚖️ Услуги":
        await message.answer(
            "⚖️ <b>Наши услуги:</b>\n\n"
            "🏛️ Недвижимость\n"
            "⚖️ Семейные дела\n"
            "📜 Наследство\n"
            "💰 Налоговые споры\n"
            "🛡️ Защита прав потребителей\n"
            "💼 Трудовые споры"
        )
    else:
        await message.answer(
            "💰 <b>Цены:</b>\n\n"
            "От 3 000 ₽ до 10 000 ₽\n"
            "Точная стоимость после консультации"
        )

# ============ СИСТЕМА ОПЕРАТОРА ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
async def call_operator(message: Message, state: FSMContext):
    logger.info(f"👨‍⚖️ Запрос от {message.from_user.id}")
    
    # Если это админ — предупреждаем
    if is_admin(message.from_user.id):
        await message.answer(
            "⚠️ Вы администратор!\n"
            "Этот режим для клиентов.\n"
            "Используйте /stop для выхода."
        )
        return
    
    await state.set_state(ChatState.operator_active)
    
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "Опишите вашу ситуацию подробно. "
        "Иван Серко ответит в ближайшее время.\n\n"
        "Для отмены нажмите ❌ Завершить разговор",
        reply_markup=operator_menu()
    )
    
    # Уведомление админу
    user = message.from_user
    notif = (
        f"🔔 <b>Новый клиент!</b>\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 <code>{user.id}</code>\n"
        f"📱 @{user.username or 'нет'}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"Клиент готов к диалогу"
    )
    
    try:
        await bot.send_message(
            ADMIN_ID, 
            notif, 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{user.id}")]
            ])
        )
        active_chats[user.id] = {
            "name": user.full_name, 
            "username": user.username,
            "time": datetime.now()
        }
        logger.info(f"✅ Уведомлен админ о {user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await message.answer("⚠️ Ошибка связи. Звоните: +7 (977) 42-32-473")

@dp.message(F.text == "❌ Завершить разговор")
async def end_chat(message: Message, state: FSMContext):
    """Завершение диалога клиентом"""
    current = await state.get_state()
    uid = message.from_user.id
    
    logger.info(f"🛑 Завершение от {uid}, состояние: {current}")
    
    if current == ChatState.operator_active.state:
        # Уведомляем админа
        if uid in active_chats:
            try:
                await bot.send_message(
                    ADMIN_ID, 
                    f"❌ Клиент <b>{active_chats[uid]['name']}</b> завершил разговор"
                )
                del active_chats[uid]
            except Exception as e:
                logger.error(f"Ошибка уведомления: {e}")
        
        await state.clear()
        await state.set_state(ChatState.automatic)
        await message.answer(
            "✅ Разговор завершён.\nСпасибо за обращение!",
            reply_markup=main_menu()
        )
    else:
        await message.answer("Вы не в режиме разговора")

@dp.message(F.text == "📞 Позвонить")
async def show_phone(message: Message):
    await message.answer("📞 +7 (977) 42-32-473")

# ============ ПЕРЕСЫЛКА В РЕЖИМЕ ОПЕРАТОРА ============
@dp.message(ChatState.operator_active)
async def forward_to_admin(message: Message, state: FSMContext):
    """Пересылка сообщений клиента админу"""
    uid = message.from_user.id
    
    # ⚠️ ВАЖНО: Если это админ — не пересылаем, а обрабатываем как команду
    if is_admin(uid):
        logger.info(f"👮 Админ {uid} пишет в режиме оператора")
        
        # Проверяем, не команда ли это
        if message.text and message.text.startswith('/'):
            # Обрабатываем команды вручную
            if message.text == '/stop':
                await cmd_stop(message, state)
            elif message.text == '/id':
                await cmd_id(message)
            elif message.text == '/chats':
                await admin_chats(message)
            else:
                await message.answer("Команда не распознана. Используйте /stop для выхода")
            return
        
        # Если не команда — предупреждаем
        await message.answer(
            "⚠️ Вы в режиме оператора как клиент.\n"
            "Ваши сообщения пересылаются вам же как админу.\n\n"
            "Напишите /stop чтобы выйти"
        )
        return
    
    # Обычный клиент — пересылаем админу
    user = message.from_user
    header = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n⏰ {datetime.now().strftime('%H:%M')}\n—\n\n"
    
    try:
        if message.text:
            await bot.send_message(
                ADMIN_ID, 
                header + message.text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
                ])
            )
        elif message.photo:
            await bot.send_photo(
                ADMIN_ID, 
                message.photo[-1].file_id, 
                caption=(header + (message.caption or ""))[:1024]
            )
        elif message.document:
            await bot.send_document(
                ADMIN_ID, 
                message.document.file_id,
                caption=(header + (message.caption or ""))[:1024]
            )
        elif message.voice:
            await bot.send_message(ADMIN_ID, header + "🎤 Голосовое:")
            await bot.send_voice(ADMIN_ID, message.voice.file_id)
        
        # Подтверждение клиенту только первый раз
        data = await state.get_data()
        if not data.get('notified'):
            await state.update_data(notified=True)
            await message.answer("✅ Сообщение отправлено юристу. Ожидайте ответа...")
            
    except Exception as e:
        logger.error(f"❌ Ошибка пересылки: {e}")
        await message.answer("⚠️ Ошибка отправки. Позвоните: +7 (977) 42-32-473")

# ============ АДМИН: ОТВЕТ ============
@dp.callback_query(F.data.startswith("reply:"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    uid = int(callback.data.split(":")[1])
    await state.update_data(reply_to=uid)
    await state.set_state("admin_replying")
    
    await callback.message.answer(
        f"✍️ <b>Режим ответа</b>\n"
        f"Клиент ID: <code>{uid}</code>\n\n"
        f"Отправьте сообщение.\n"
        f"/cancel — отмена\n"
        f"/stop — выйти из режима оператора"
    )
    await callback.answer()

@dp.message(Command("cancel"), State("admin_replying"))
async def admin_cancel(message: Message, state: FSMContext):
    if is_admin(message.from_user.id):
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())

@dp.message(State("admin_replying"))
async def admin_send(message: Message, state: FSMContext):
    """Админ отправляет ответ клиенту"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    uid = data.get('reply_to')
    
    if not uid:
        await message.answer("❌ Ошибка: клиент не найден")
        await state.clear()
        return
    
    try:
        header = "👨‍⚖️ <b>Иван Серко (юрист):</b>\n\n"
        
        if message.text:
            await bot.send_message(uid, header + message.text)
        elif message.photo:
            await bot.send_photo(uid, message.photo[-1].file_id, caption=header + (message.caption or ""))
        elif message.document:
            await bot.send_document(uid, message.document.file_id, caption=header + (message.caption or ""))
        elif message.voice:
            await bot.send_voice(uid, message.voice.file_id, caption=header)
        
        await message.answer(f"✅ Отправлено клиенту {uid}")
        logger.info(f"✅ Админ ответил {uid}")
        
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
    
    text = "📋 <b>Активные чаты:</b>\n\n"
    for uid, info in active_chats.items():
        text += f"• <b>{info['name']}</b>\n"
        text += f"  🆔 <code>{uid}</code>\n"
        if info['username']:
            text += f"  📱 @{info['username']}\n"
        text += f"  ⏰ {info['time'].strftime('%H:%M')}\n\n"
    
    await message.answer(text)

# ============ ЛЮБОЙ ДРУГОЙ ТЕКСТ ============
@dp.message(ChatState.automatic)
async def any_text(message: Message):
    """Обработка неизвестных сообщений"""
    logger.info(f"💬 Текст от {message.from_user.id}: {message.text[:30]}...")
    await message.answer(
        "Я не понял команду. Выберите действие из меню 👇",
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

async def on_shutdown(app: web.Application = None):
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.router.add_get("/", lambda r: web.Response(text=f"Bot OK. ADMIN: {ADMIN_ID}"))
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
