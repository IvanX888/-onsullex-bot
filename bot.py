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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID}")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

# ============ FSM ============
class ChatState(StatesGroup):
    bot_chat = State()      # Общение с ботом (автоответы)
    operator_chat = State() # Общение с оператором

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# Хранилище: user_id -> количество сообщений
user_stats = {}
# Хранилище активных диалогов с оператором
active_dialogs = {}

# ============ КЛАВИАТУРЫ ============
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку"), KeyboardButton(text="👨‍⚖️ Связаться с юристом")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="❓ Задать вопрос")]
        ],
        resize_keyboard=True
    )

def bot_chat_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👨‍⚖️ Связаться с юристом")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="❓ FAQ")]
        ],
        resize_keyboard=True
    )

def operator_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📞 Телефон для связи")],
            [KeyboardButton(text="❓ FAQ")]
        ],
        resize_keyboard=True
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить диалог с клиентом")],
            [KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

# ============ ПРОВЕРКА ============
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ ГОТОВЫЕ ОТВЕТЫ БОТА ============
BOT_ANSWERS = {
    "привет": "👋 Здравствуйте! Я помогу вам с юридическими вопросами. Что вас интересует?",
    "здравствуйте": "👋 Добрый день! Готов помочь. Выберите тему или задайте вопрос.",
    "цена": "💰 Стоимость консультации от 3 000 ₽. Точная цена зависит от сложности вопроса.\n\nДля расчёта нажмите 👨‍⚖️ Связаться с юристом",
    "стоимость": "💰 Консультация от 3 000 ₽. Подробнее по телефону +7 (977) 42-32-473",
    "услуги": "⚖️ Мы помогаем с:\n• Недвижимость\n• Семейные дела\n• Наследство\n• Налоги\n• Трудовые споры\n\nПодробности в меню ⚖️ Услуги",
    "контакты": "📞 +7 (977) 42-32-473\n📧 333742917@mail.ru\n🕐 9:00-21:00",
    "телефон": "📞 +7 (977) 42-32-473 (WhatsApp/Telegram)",
    "адрес": "🏛️ г. Москва, офис по договорённости",
    "время": "🕐 Работаем ежедневно 9:00-21:00",
    "спасибо": "🙏 Пожалуйста! Обращайтесь, если будут вопросы.",
    "до свидания": "👋 До свидания! Хорошего дня!",
    "пока": "👋 До встречи!",
}

# ============ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    logger.info(f"🚀 /start от {uid}")
    
    await state.clear()
    await state.set_state(ChatState.bot_chat)
    
    # Сбрасываем счётчик
    user_stats[uid] = 0
    
    welcome = f"""
👑 <b>Добро пожаловать в Консуллекс!</b>

Здравствуйте, {message.from_user.first_name}!

Я — юридический помощник. Задайте вопрос, и я постараюсь помочь.

<b>Что я умею:</b>
• Отвечать на частые вопросы
• Рассказать об услугах и ценах
• Соединить с юристом (после 3 вопросов или по запросу)

Ваш ID: <code>{uid}</code>
    """
    
    if is_admin(uid):
        welcome += "\n\n🔐 <b>Вы администратор</b>"
        await message.answer(welcome, reply_markup=main_menu(), parse_mode=ParseMode.HTML)
        await message.answer("Админ-команды: /stop — завершить любой диалог")
    else:
        await message.answer(welcome, reply_markup=main_menu(), parse_mode=ParseMode.HTML)

@dp.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    """Админская команда для сброса любого состояния"""
    if not is_admin(message.from_user.id):
        return
    
    uid = message.from_user.id
    
    # Если админ в диалоге с клиентом
    if uid in active_dialogs:
        client_id = active_dialogs[uid]
        try:
            await bot.send_message(client_id, "👨‍⚖️ Юрист завершил консультацию. Если есть вопросы — обращайтесь!", reply_markup=main_menu())
            await state.clear()
            await state.set_state(ChatState.bot_chat)
            del active_dialogs[uid]
            await message.answer(f"✅ Диалог с клиентом {client_id} завершён", reply_markup=main_menu())
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
        return
    
    await state.clear()
    await state.set_state(ChatState.bot_chat)
    await message.answer("✅ Состояние сброшено", reply_markup=main_menu())

# ============ МЕНЮ ============
@dp.message(F.text == "📝 Оставить заявку")
async def menu_request(message: Message):
    await message.answer(
        "📞 <b>Оставить заявку:</b>\n\n"
        "📱 WhatsApp/Telegram: +7 (977) 42-32-473\n"
        "📧 Email: 333742917@mail.ru\n\n"
        "⏰ Ответим в течение 15 минут!"
    )

@dp.message(F.text == "⚖️ Услуги")
async def menu_services(message: Message):
    await message.answer(
        "⚖️ <b>Наши услуги:</b>\n\n"
        "🏛️ <b>Недвижимость</b>\n"
        "• Проверка документов\n"
        "• Сопровождение сделок\n"
        "• Споры с застройщиками\n\n"
        "⚖️ <b>Семейные дела</b>\n"
        "• Разводы и раздел имущества\n"
        "• Алименты\n"
        "• Опека и guardianship\n\n"
        "📜 <b>Наследство</b>\n"
        "• Оформление\n"
        "• Оспаривание завещаний\n\n"
        "💰 <b>Налоговые споры</b>\n"
        "• Споры с ФНС\n"
        "• Возврат налогов\n\n"
        "💼 <b>Трудовые споры</b>\n"
        "• Увольнения\n"
        "• Долги по зарплате"
    )

@dp.message(F.text == "💰 Цены")
async def menu_prices(message: Message):
    await message.answer(
        "💰 <b>Стоимость услуг:</b>\n\n"
        "📝 <b>Консультация</b> — от 3 000 ₽\n"
        "📄 <b>Составление документов</b> — от 5 000 ₽\n"
        "⚖️ <b>Представительство в суде</b> — от 15 000 ₽\n\n"
        "💡 Точная стоимость после изучения дела.\n"
        "👨‍⚖️ Нажмите «Связаться с юристом» для расчёта."
    )

@dp.message(F.text == "📞 Контакты")
async def menu_contacts(message: Message):
    await message.answer(
        "📞 <b>Контакты:</b>\n\n"
        "📱 Телефон/WhatsApp: +7 (977) 42-32-473\n"
        "📧 Email: 333742917@mail.ru\n"
        "🕐 Режим работы: 9:00-21:00, ежедневно\n"
        "🏛️ Адрес: г. Москва (по договорённости)"
    )

@dp.message(F.text == "❓ Задать вопрос")
async def menu_faq(message: Message):
    await message.answer(
        "❓ <b>Задайте вопрос!</b>\n\n"
        "Я отвечу на типовые вопросы. Если нужна конкретная помощь — нажмите 👨‍⚖️ Связаться с юристом\n\n"
        "Примеры вопросов:\n"
        "• Сколько стоит консультация?\n"
        "• Какие услуги вы оказываете?\n"
        "• Как с вами связаться?"
    )

# ============ ПЕРЕКЛЮЧЕНИЕ НА ОПЕРАТОРА ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
async def call_operator(message: Message, state: FSMContext):
    uid = message.from_user.id
    
    # Админ не может стать клиентом
    if is_admin(uid):
        await message.answer("⚠️ Вы администратор. Эта функция для клиентов.")
        return
    
    current_state = await state.get_state()
    
    # Если уже в режиме оператора
    if current_state == ChatState.operator_chat.state:
        await message.answer("✅ Вы уже на связи с юристом. Пишите ваш вопрос.")
        return
    
    logger.info(f"👨‍⚖️ Клиент {uid} переключился на оператора")
    
    await state.set_state(ChatState.operator_chat)
    
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "✅ <b>Иван Серко</b> получил уведомление и скоро ответит.\n\n"
        "Опишите вашу ситуацию подробно:\n"
        "• В чём проблема?\n"
        "• Когда возникла?\n"
        "• Какие документы есть?\n\n"
        "💡 Можете отправить фото документов.",
        reply_markup=operator_menu()
    )
    
    # Уведомление админу
    user = message.from_user
    try:
        msg = await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Новый клиент на связи!</b>\n\n"
            f"👤 Имя: {user.full_name}\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📱 @{user.username or 'нет'}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Клиент ждёт ответа...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить клиенту", callback_data=f"reply:{uid}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        
        # Сохраняем связь: admin_msg_id -> client_id
        active_dialogs[ADMIN_ID] = uid
        
        logger.info(f"✅ Админ уведомлён о клиенте {uid}")
    except Exception as e:
        logger.error(f"❌ Ошибка уведомления: {e}")
        await message.answer("⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473")

@dp.message(F.text == "📞 Телефон для связи")
async def operator_phone(message: Message):
    await message.answer("📞 +7 (977) 42-32-473 (WhatsApp/Telegram)")

# ============ ОБЩЕНИЕ С БОТОМ (АВТООТВЕТЫ) ============
@dp.message(ChatState.bot_chat)
async def bot_chat_handler(message: Message, state: FSMContext):
    """Обработка сообщений в режиме бота"""
    uid = message.from_user.id
    text = message.text.lower()
    
    # Увеличиваем счётчик сообщений
    user_stats[uid] = user_stats.get(uid, 0) + 1
    count = user_stats[uid]
    
    logger.info(f"🤖 Бот-чат с {uid}, сообщение #{count}: {text[:50]}")
    
    # Ищем готовый ответ
    answer = None
    for key, resp in BOT_ANSWERS.items():
        if key in text:
            answer = resp
            break
    
    # Если нет готового ответа
    if not answer:
        if "?" in text or "как" in text or "что" in text or "можно" in text:
            answer = "🤔 Интересный вопрос! Для точного ответа рекомендую связаться с юристом — нажмите 👨‍⚖️ Связаться с юристом"
        else:
            answer = "👋 Я вас понял! Если нужна конкретная помощь — выберите пункт меню или нажмите 👨‍⚖️ Связаться с юристом"
    
    # После 3 сообщений предлагаем связаться с юристом
    if count >= 3 and count % 3 == 0:
        answer += "\n\n💡 <b>Совет:</b> Для сложных вопросов лучше проконсультироваться лично. Нажмите 👨‍⚖️ Связаться с юристом"
    
    await message.answer(answer, reply_markup=bot_chat_menu())

# ============ ОБЩЕНИЕ С ОПЕРАТОРОМ ============
@dp.message(ChatState.operator_chat)
async def operator_chat_handler(message: Message, state: FSMContext):
    """Обработка сообщений в режиме оператора"""
    uid = message.from_user.id
    
    # Если это админ пишет (не должно произойти, но на всякий случай)
    if is_admin(uid):
        return
    
    user = message.from_user
    logger.info(f"💬 Клиент {uid} -> Админ: {message.text[:50] if message.text else '[фото/документ]'}")
    
    try:
        # Текст
        if message.text:
            await bot.send_message(
                ADMIN_ID,
                f"💬 <b>{user.full_name}</b>\n"
                f"🆔 <code>{uid}</code>\n"
                f"⏰ {datetime.now().strftime('%H:%M')}\n"
                f"—\n\n"
                f"{message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
                ]),
                parse_mode=ParseMode.HTML
            )
        
        # Фото
        elif message.photo:
            caption = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n⏰ {datetime.now().strftime('%H:%M')}\n—\n\n" + (message.caption or "🖼️ Фото")
            await bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,
                caption=caption[:1024],
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
                ])
            )
        
        # Документ
        elif message.document:
            caption = f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n⏰ {datetime.now().strftime('%H:%M')}\n—\n\n" + (message.caption or "📄 Документ")
            await bot.send_document(
                ADMIN_ID,
                message.document.file_id,
                caption=caption[:1024],
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
                ])
            )
        
        # Голосовое
        elif message.voice:
            await bot.send_message(
                ADMIN_ID,
                f"💬 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n⏰ {datetime.now().strftime('%H:%M')}\n—\n\n🎤 Голосовое сообщение:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{uid}")]
                ])
            )
            await bot.send_voice(ADMIN_ID, message.voice.file_id)
        
        # Подтверждение клиенту (только первый раз)
        data = await state.get_data()
        if not data.get('connected'):
            await state.update_data(connected=True)
            await message.answer("✅ Сообщение доставлено юристу. Ожидайте ответа...")
        
    except Exception as e:
        logger.error(f"❌ Ошибка пересылки: {e}")
        await message.answer("⚠️ Ошибка отправки. Позвоните: +7 (977) 42-32-473")

# ============ АДМИН: ОТВЕТ КЛИЕНТУ ============
@dp.callback_query(F.data.startswith("reply:"))
async def admin_reply_callback(callback: types.CallbackQuery, state: FSMContext):
    """Админ нажал кнопку Ответить"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    uid = int(callback.data.split(":")[1])
    
    # Сохраняем ID клиента для ответа
    await state.update_data(reply_to=uid)
    
    await callback.message.answer(
        f"✍️ <b>Режим ответа клиенту</b>\n\n"
        f"Клиент ID: <code>{uid}</code>\n\n"
        f"Отправьте сообщение (текст, фото, документ или голосовое).\n"
        f"Оно будет доставлено клиенту.\n\n"
        f"Для выхода нажмите ❌ Завершить диалог с клиентом",
        reply_markup=admin_menu()
    )
    await callback.answer()

@dp.message(F.text == "❌ Завершить диалог с клиентом")
async def admin_end_dialog(message: Message, state: FSMContext):
    """Админ завершает диалог с клиентом"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    client_id = data.get('reply_to')
    
    if not client_id:
        await message.answer("❌ Нет активного диалога для завершения")
        return
    
    try:
        # Отправляем клиенту уведомление
        await bot.send_message(
            client_id,
            "👨‍⚖️ <b>Консультация завершена</b>\n\n"
            "Юрист закончил диалог. Если остались вопросы — нажмите 👨‍⚖️ Связаться с юристом снова или выберите пункт меню.",
            reply_markup=main_menu(),
            parse_mode=ParseMode.HTML
        )
        
        # Удаляем из активных диалогов
        if message.from_user.id in active_dialogs:
            del active_dialogs[message.from_user.id]
        
        await message.answer(
            f"✅ Диалог с клиентом {client_id} завершён.\n"
            f"Клиент возвращён к боту.",
            reply_markup=main_menu()
        )
        
        logger.info(f"✅ Админ завершил диалог с {client_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка завершения: {e}")
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    """Статистика для админа"""
    if not is_admin(message.from_user.id):
        return
    
    active_count = len(active_dialogs)
    await message.answer(
        f"📊 <b>Статистика:</b>\n\n"
        f"🟢 Активных диалогов: {active_count}\n"
        f"👥 Всего уникальных пользователей: {len(user_stats)}"
    )

# ============ АДМИН: ОТПРАВКА СООБЩЕНИЯ ============
@dp.message()
async def admin_send_message(message: Message, state: FSMContext):
    """Обработка сообщений админа (ответы клиентам)"""
    # Если не админ — игнорируем (уже обработано выше)
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    client_id = data.get('reply_to')
    
    # Если нет активного клиента для ответа
    if not client_id:
        # Проверяем, не команда ли это
        if message.text and message.text.startswith('/'):
            return  # Пусть обработчики команд сами разбираются
        
        await message.answer(
            "ℹ️ Нет активного диалога.\n\n"
            "Чтобы ответить клиенту:\n"
            "1. Дождитесь сообщения от клиента\n"
            "2. Нажмите кнопку «✍️ Ответить» под его сообщением\n"
            "3. Или используйте /stop для сброса"
        )
        return
    
    # Отправляем клиенту
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
        
        await message.answer(f"✅ Отправлено клиенту {client_id}")
        logger.info(f"✅ Админ ответил клиенту {client_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        await message.answer(f"❌ Ошибка: {e}\n\nВозможно, клиент заблокировал бота.")

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
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook: {webhook_url}")

async def on_shutdown(app: web.Application = None):
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
