import os
import logging
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
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
active_chats = {}  # user_id -> {name, username}

# ============ МЕНЮ ============
def main_menu(is_admin=False):
    if is_admin:
        # У админа нет кнопки "Связаться с юристом"
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📝 Оставить заявку")],
                [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
                [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="📋 Документы")],
                [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="⭐ Отзывы")]
            ],
            resize_keyboard=True
        )
    else:
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

# ============ ПРОВЕРКА ============
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    logger.info(f"/start от {uid}")
    
    await state.clear()
    await state.set_state(ChatState.automatic)
    
    admin = is_admin(uid)
    menu = main_menu(is_admin=admin)
    
    text = f"👑 Добро пожаловать, {message.from_user.first_name}!\nВаш ID: <code>{uid}</code>"
    if admin:
        text += "\n\n🔐 Вы администратор"
    
    await message.answer(text, reply_markup=menu, parse_mode=ParseMode.HTML)

@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    """Аварийный сброс"""
    await state.clear()
    await state.set_state(ChatState.automatic)
    await message.answer("✅ Сброшено", reply_markup=main_menu(is_admin=is_admin(message.from_user.id)))

@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>")

# ============ ОБРАБОТКА КНОПКИ СВЯЗИ ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
async def call_operator(message: Message, state: FSMContext):
    uid = message.from_user.id
    
    # Защита: админ не может быть клиентом
    if is_admin(uid):
        await message.answer("⚠️ Вы админ. Это для клиентов.")
        return
    
    logger.info(f"Клиент {uid} запросил оператора")
    await state.set_state(ChatState.operator_active)
    
    await message.answer(
        "⏳ Соединяю с юристом...\nОпишите ситуацию:",
        reply_markup=operator_menu()
    )
    
    # Уведомление админу
    user = message.from_user
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 Новый клиент!\n👤 {user.full_name}\n🆔 <code>{uid}</code>\n📱 @{user.username or 'нет'}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
            ])
        )
        active_chats[uid] = {"name": user.full_name, "username": user.username}
        logger.info(f"Уведомлен админ о {uid}")
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")

@dp.message(F.text == "❌ Завершить разговор")
async def end_chat(message: Message, state: FSMContext):
    current = await state.get_state()
    if current != ChatState.operator_active.state:
        await message.answer("Вы не в режиме разговора")
        return
    
    uid = message.from_user.id
    
    # Уведомляем админа
    if uid in active_chats:
        try:
            await bot.send_message(ADMIN_ID, f"❌ Клиент {active_chats[uid]['name']} вышел")
            del active_chats[uid]
        except: pass
    
    await state.clear()
    await state.set_state(ChatState.automatic)
    await message.answer("✅ Завершено", reply_markup=main_menu(is_admin=is_admin(uid)))

@dp.message(F.text == "📞 Позвонить")
async def show_phone(message: Message):
    await message.answer("📞 +7 (977) 42-32-473")

# ============ ПЕРЕСЫЛКА ============
@dp.message(ChatState.operator_active)
async def forward_to_admin(message: Message, state: FSMContext):
    uid = message.from_user.id
    
    # Если админ каким-то образом здесь — игнорируем
    if is_admin(uid):
        return
    
    user = message.from_user
    
    try:
        if message.text:
            text = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n—\n\n{message.text}"
            await bot.send_message(ADMIN_ID, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
            ]))
        elif message.photo:
            caption = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n—\n\n" + (message.caption or "")
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption[:1024])
        elif message.document:
            caption = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n—\n\n" + (message.caption or "")
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=caption[:1024])
        elif message.voice:
            await bot.send_message(ADMIN_ID, f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n—\n\n🎤 Голосовое:")
            await bot.send_voice(ADMIN_ID, message.voice.file_id)
        
        # Подтверждение клиенту (только первый раз)
        data = await state.get_data()
        if not data.get('notified'):
            await state.update_data(notified=True)
            await message.answer("✅ Отправлено юристу. Ждите ответа...")
            
    except Exception as e:
        logger.error(f"Ошибка пересылки: {e}")

# ============ АДМИН: ОТВЕТ ============
@dp.callback_query(F.data.startswith("reply:"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    uid = int(callback.data.split(":")[1])
    await state.update_data(reply_to=uid)
    
    # Важно: НЕ меняем состояние FSM, чтобы не сломать автоматический режим
    # Просто запоминаем ID для ответа
    await callback.message.answer(f"✍️ Ответ клиенту {uid}:\nОтправьте сообщение (текст/фото/голос)")
    await callback.answer()

@dp.message(F.reply_to_message)
async def admin_reply_via_reply(message: Message, state: FSMContext):
    """Альтернативный способ: ответить через Reply на сообщение клиента"""
    if not is_admin(message.from_user.id):
        return
    
    # Извлекаем ID из текста сообщения (формат: "💬 Имя\n🆔 123456789\n—")
    original = message.reply_to_message.text or message.reply_to_message.caption or ""
    
    # Ищем ID в тексте
    import re
    match = re.search(r'🆔 (\d+)', original)
    if not match:
        await message.answer("❌ Не могу найти ID клиента. Используйте кнопку 'Ответить'")
        return
    
    uid = int(match.group(1))
    
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
        await message.answer(f"❌ Ошибка: {e}")

# ============ ОСТАЛЬНОЕ МЕНЮ ============
@dp.message(F.text == "📝 Оставить заявку")
async def menu_request(message: Message):
    await message.answer("📞 Звоните: +7 (977) 42-32-473\n📧 333742917@mail.ru")

@dp.message(F.text == "⚖️ Услуги")
async def menu_services(message: Message):
    await message.answer("⚖️ Недвижимость, семейные дела, наследство, налоги...")

@dp.message(F.text == "💰 Цены")
async def menu_prices(message: Message):
    await message.answer("💰 От 3 000 ₽. Уточняйте по телефону.")

@dp.message(F.text == "📞 Контакты")
async def menu_contacts(message: Message):
    await message.answer("📞 +7 (977) 42-32-473\n📧 333742917@mail.ru\n🕐 9:00-21:00")

@dp.message(F.text == "📋 Документы")
async def menu_docs(message: Message):
    await message.answer("📋 Документы по запросу")

@dp.message(F.text == "❓ FAQ")
async def menu_faq(message: Message):
    await message.answer("❓ Частые вопросы:\n• Юрист vs Адвокат\n• Представительство в суде")

@dp.message(F.text == "⭐ Отзывы")
async def menu_reviews(message: Message):
    await message.answer("⭐ Отличные отзывы клиентов!")

@dp.message(ChatState.automatic)
async def any_text(message: Message):
    await message.answer("Выберите действие из меню 👇")

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

app = web.Application()
app.router.add_post("/webhook", handle_webhook)
app.router.add_get("/", lambda r: web.Response(text=f"Bot OK. ADMIN: {ADMIN_ID}"))
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    web.run_app(app, host="0.0.0.0", port=port)
