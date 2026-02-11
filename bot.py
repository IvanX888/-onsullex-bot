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
ADMIN_ID = os.getenv("ADMIN_ID", "717849646")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL не установлен!")

# ============ FSM СОСТОЯНИЯ ============
class ChatState(StatesGroup):
    automatic = State()      # Автоматический режим
    waiting_operator = State()  # Ожидание оператора
    operator_active = State()   # Оператор в чате

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# Хранилище активных чатов с оператором (user_id -> operator_message_id mapping)
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
    """Меню когда активен оператор"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Завершить разговор с юристом")],
            [KeyboardButton(text="📞 Телефон для связи")]
        ],
        resize_keyboard=True
    )

def admin_reply_keyboard(user_id):
    """Клавиатура для админа для ответа конкретному пользователю"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_to:{user_id}")]
    ])

# ============ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(ChatState.automatic)
    welcome_text = f"""
👑 <b>Добро пожаловать в Консуллекс!</b>

Здравствуйте, {message.from_user.first_name}!

Я — личный помощник <b>Ивана Серко</b>, частного юриста премиум-класса.

<b>Чем могу помочь:</b>
• 📝 Приму заявку 24/7
• ⚖️ Расскажу об услугах  
• 💰 Сообщу цены
• ❓ Отвечу на вопросы
• 👨‍⚖️ <b>Соединю с юристом</b> для сложных вопросов
• 📋 Дам документы
• 📞 Предоставлю контакты

⚖️ <i>Власть права в ваших руках</i>
    """
    await message.answer(welcome_text, reply_markup=main_menu())

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — начать работу\n"
        "/help — помощь\n"
        "/ping — проверить работу\n"
        "/operator — связаться с юристом\n"
        "/stop — завершить разговор с юристом"
    )

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong! Бот работает исправно.")

# ============ ОСНОВНОЕ МЕНЮ ============
@dp.message(F.text == "📝 Оставить заявку")
async def start_request(message: types.Message):
    await message.answer(
        "📞 <b>Свяжитесь напрямую:</b>\n\n"
        "📱 <b>WhatsApp/Telegram:</b>\n"
        "+7 (977) 42-32-473\n\n"
        "📧 <b>Email:</b>\n"
        "333742917@mail.ru\n\n"
        "⏰ <b>Отвечаю в течение 15 минут</b>"
    )

@dp.message(F.text == "⚖️ Услуги")
async def show_services(message: types.Message):
    await message.answer(
        "⚖️ <b>Наши услуги:</b>\n\n"
        "🏛️ <b>Недвижимость</b>\n"
        "• Проверка документов\n"
        "• Сопровождение сделок\n"
        "• Споры с застройщиками\n\n"
        "⚖️ <b>Семейные дела</b>\n"
        "• Разводы\n"
        "• Раздел имущества\n"
        "• Алименты\n\n"
        "📜 <b>Наследство</b>\n"
        "• Оформление\n"
        "• Оспаривание\n"
        "• Восстановление сроков\n\n"
        "💰 <b>Налоговые споры</b>\n"
        "• ФНС\n"
        "• Штрафы\n"
        "• Вычеты\n\n"
        "🛡️ <b>Защита прав потребителей</b>\n"
        "• Возвраты\n"
        "• Компенсации\n"
        "• Неустойки\n\n"
        "💼 <b>Трудовые споры</b>\n"
        "• Увольнения\n"
        "• Долги по зарплате\n"
        "• Восстановление"
    )

@dp.message(F.text == "💰 Цены")
async def show_prices(message: types.Message):
    await message.answer(
        "💰 <b>Цены на услуги:</b>\n\n"
        "🏛️ <b>Недвижимость</b> — от 5 000 ₽\n"
        "⚖️ <b>Семейные дела</b> — от 4 000 ₽\n"
        "📜 <b>Наследство</b> — от 6 000 ₽\n"
        "💰 <b>Налоговые споры</b> — от 4 000 ₽\n"
        "🛡️ <b>Защита прав</b> — от 3 000 ₽\n"
        "💼 <b>Трудовые споры</b> — от 4 000 ₽\n\n"
        "📞 <b>Уточняйте по телефону:</b>\n"
        "+7 (977) 42-32-473"
    )

@dp.message(F.text == "📞 Контакты")
async def show_contacts(message: types.Message):
    await message.answer(
        "📞 <b>Контакты Консуллекс:</b>\n\n"
        "📱 <b>WhatsApp/Telegram:</b>\n"
        "+7 (977) 42-32-473\n\n"
        "📧 <b>Email:</b>\n"
        "333742917@mail.ru\n\n"
        "🕐 <b>Режим работы:</b>\n"
        "9:00 — 21:00, ежедневно\n\n"
        "🏛️ <b>Офис:</b>\n"
        "г. Москва (по договорённости)"
    )

@dp.message(F.text == "📋 Документы")
async def show_documents(message: types.Message):
    await message.answer(
        "📋 <b>Полезные документы:</b>\n\n"
        "📄 <b>Чек-лист на консультацию</b>\n"
        "Что взять с собой\n\n"
        "📄 <b>Образец договора</b>\n"
        "Предоставляется после консультации\n\n"
        "📄 <b>Памятка клиенту</b>\n"
        "Как подготовиться\n\n"
        "📞 <b>Запросите у юриста:</b>\n"
        "+7 (977) 42-32-473"
    )

@dp.message(F.text == "❓ FAQ")
async def show_faq(message: types.Message):
    await message.answer(
        "❓ <b>Частые вопросы:</b>\n\n"
        "⚖️ <b>Чем юрист отличается от адвоката?</b>\n"
        "Адвокат — для уголовных дел\n"
        "Юрист — для гражданских дел\n\n"
        "⚖️ <b>Можете представлять в суде?</b>\n"
        "Да, в гражданских и арбитражных делах\n\n"
        "⚖️ <b>Как проходит консультация?</b>\n"
        "Онлайн или лично, 1+ часа\n\n"
        "⚖️ <b>Какие гарантии?</b>\n"
        "Возврат денег если помощь не требуется\n\n"
        "⚖️ <b>Какие документы нужны?</b>\n"
        "Паспорт + документы по вопросу"
    )

@dp.message(F.text == "⭐ Отзывы")
async def show_reviews(message: types.Message):
    await message.answer(
        "⭐ <b>Отзывы клиентов:</b>\n\n"
        "★★★★★ <b>Анна, Москва</b>\n"
        "«Помог с возвратом денег за квартиру. Результат за 2 недели!»\n\n"
        "★★★★★ <b>Дмитрий, СПб</b>\n"
        "«Раздел имущества после развода. Всё четко, без эмоций.»\n\n"
        "★★★★★ <b>Ольга, Казань</b>\n"
        "«Наследство оформили быстро. Юрист на связи 24/7.»\n\n"
        "📝 <b>Оставить отзыв:</b>\n"
        "Напишите на 333742917@mail.ru"
    )

# ============ СИСТЕМА ОПЕРАТОРА ============
@dp.message(F.text == "👨‍⚖️ Связаться с юристом")
@dp.message(Command("operator"))
async def call_operator(message: types.Message, state: FSMContext):
    """Пользователь запрашивает связь с юристом"""
    await state.set_state(ChatState.waiting_operator)
    
    # Информируем пользователя
    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "Ваш вопрос будет передан Ивану Серко лично. "
        "Обычно ответ занимает 5-15 минут.\n\n"
        "Опишите вашу ситуацию подробно — это поможет быстрее помочь вам.",
        reply_markup=operator_menu()
    )
    
    # Отправляем уведомление админу
    user = message.from_user
    notification = (
        f"🔔 <b>Новый запрос на консультацию!</b>\n\n"
        f"👤 <b>Клиент:</b> {user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"📱 <b>Username:</b> @{user.username or 'нет'}\n"
        f"⏰ <b>Время:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"💬 <b>Сообщение:</b>\n{message.text if message.text not in ['👨‍⚖️ Связаться с юристом', '/operator'] else '<i>Ожидает первого сообщения...</i>'}"
    )
    
    try:
        admin_msg = await bot.send_message(
            chat_id=ADMIN_ID,
            text=notification,
            reply_markup=admin_reply_keyboard(user.id)
        )
        # Сохраняем связь user_id -> admin_message_id для ответов
        active_chats[user.id] = {
            'admin_msg_id': admin_msg.message_id,
            'username': user.username,
            'full_name': user.full_name
        }
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")
        await message.answer("⚠️ Произошла ошибка. Попробуйте позже или позвоните: +7 (977) 42-32-473")

@dp.message(F.text == "❌ Завершить разговор с юристом")
@dp.message(Command("stop"))
async def end_operator_chat(message: types.Message, state: FSMContext):
    """Завершение разговора с оператором"""
    current_state = await state.get_state()
    
    if current_state in [ChatState.waiting_operator.state, ChatState.operator_active.state]:
        user_id = message.from_user.id
        
        # Уведомляем админа
        if user_id in active_chats:
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Клиент <b>{active_chats[user_id]['full_name']}</b> (ID: <code>{user_id}</code>) завершил разговор."
                )
                del active_chats[user_id]
            except:
                pass
        
        await state.set_state(ChatState.automatic)
        await message.answer(
            "✅ Разговор с юристом завершён.\n\n"
            "Если появятся вопросы — обращайтесь!",
            reply_markup=main_menu()
        )
    else:
        await message.answer("Вы не находитесь в режиме разговора с юристом.")

@dp.message(F.text == "📞 Телефон для связи")
async def operator_phone(message: types.Message):
    await message.answer(
        "📞 <b>Прямой контакт:</b>\n"
        "+7 (977) 42-32-473\n\n"
        "Работаю с 9:00 до 21:00"
    )

# ============ ОБРАБОТКА СООБЩЕНИЙ В РЕЖИМЕ ОПЕРАТОРА ============
@dp.message(ChatState.waiting_operator)
@dp.message(ChatState.operator_active)
async def message_to_operator(message: types.Message, state: FSMContext):
    """Пересылка сообщений пользователя админу"""
    user_id = message.from_user.id
    user = message.from_user
    
    # Формируем сообщение для админа
    header = f"💬 <b>Сообщение от {user.full_name}</b> (ID: <code>{user_id}</code>)\n"
    if user.username:
        header += f"@{user.username}\n"
    header += f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
    header += "—" * 20 + "\n\n"
    
    try:
        # Пересылаем текст
        if message.text:
            admin_text = header + message.text
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=admin_reply_keyboard(user_id)
            )
        
        # Пересылаем документы
        elif message.document:
            caption = header + (message.caption or "📄 Документ")
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=message.document.file_id,
                caption=caption[:1024],  # Ограничение caption
                reply_markup=admin_reply_keyboard(user_id)
            )
        
        # Пересылаем фото
        elif message.photo:
            caption = header + (message.caption or "🖼️ Фото")
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=message.photo[-1].file_id,  # Самое большое фото
                caption=caption[:1024],
                reply_markup=admin_reply_keyboard(user_id)
            )
        
        # Пересылаем голосовые
        elif message.voice:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=header + "🎤 Голосовое сообщение:",
                reply_markup=admin_reply_keyboard(user_id)
            )
            await bot.send_voice(
                chat_id=ADMIN_ID,
                voice=message.voice.file_id
            )
        
        # Другие типы
        else:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=header + "📎 Получен файл другого типа",
                reply_markup=admin_reply_keyboard(user_id)
            )
        
        # Подтверждение пользователю (только при первом сообщении)
        current_state = await state.get_state()
        if current_state == ChatState.waiting_operator.state:
            await state.set_state(ChatState.operator_active)
            await message.answer(
                "✅ <b>Сообщение отправлено юристу!</b>\n"
                "Ожидайте ответа в этом чате..."
            )
            
    except Exception as e:
        logger.error(f"Ошибка пересылки админу: {e}")
        await message.answer(
            "⚠️ Ошибка отправки сообщения. Попробуйте позже или позвоните: +7 (977) 42-32-473"
        )

# ============ АДМИН-ПАНЕЛЬ: ОТВЕТЫ ОПЕРАТОРА ============
@dp.callback_query(F.data.startswith("reply_to:"))
async def admin_start_reply(callback: CallbackQuery, state: FSMContext):
    """Админ нажал кнопку ответить"""
    if str(callback.from_user.id) != ADMIN_ID:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    user_id = int(callback.data.split(":")[1])
    
    # Сохраняем состояние админа
    await state.update_data(replying_to=user_id)
    await state.set_state("admin_replying")
    
    await callback.message.answer(
        f"✍️ <b>Режим ответа клиенту</b>\n"
        f"ID: <code>{user_id}</code>\n\n"
        f"Отправьте сообщение, и оно будет доставлено клиенту.\n"
        f"Для отмены: /cancel"
    )
    await callback.answer()

@dp.message(Command("cancel"), State("admin_replying"))
async def admin_cancel_reply(message: types.Message, state: FSMContext):
    """Админ отменил ответ"""
    await state.clear()
    await message.answer("❌ Ответ отменён.")

@dp.message(State("admin_replying"))
async def admin_send_reply(message: types.Message, state: FSMContext):
    """Админ отправляет ответ пользователю"""
    data = await state.get_data()
    user_id = data.get('replying_to')
    
    if not user_id:
        await message.answer("❌ Ошибка: клиент не найден")
        await state.clear()
        return
    
    try:
        # Отправляем пользователю
        header = "👨‍⚖️ <b>Иван Серко (юрист):</b>\n\n"
        
        if message.text:
            await bot.send_message(
                chat_id=user_id,
                text=header + message.text
            )
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
            await bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                caption=header
            )
        else:
            await message.answer("❌ Этот тип сообщений не поддерживается для ответа")
            return
        
        # Подтверждение админу
        await message.answer(
            f"✅ <b>Отправлено клиенту</b> (ID: <code>{user_id}</code>)\n\n"
            f"Отправьте ещё сообщение или /cancel для выхода"
        )
        
        # Обновляем состояние пользователя если нужно
        # (остаёмся в режиме admin_replying для возможности отправить несколько сообщений)
        
    except Exception as e:
        logger.error(f"Ошибка отправки пользователю: {e}")
        await message.answer(f"❌ Ошибка отправки: {e}")

# ============ КОМАНДА АДМИНУ ДЛЯ ПРОСМОТРА АКТИВНЫХ ЧАТОВ ============
@dp.message(Command("chats"))
async def admin_show_chats(message: types.Message):
    """Показать активные чаты"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if not active_chats:
        await message.answer("📭 Нет активных чатов")
        return
    
    text = "📋 <b>Активные чаты:</b>\n\n"
    for uid, info in active_chats.items():
        text += f"• <b>{info['full_name']}</b> (ID: <code>{uid}</code>)\n"
        if info['username']:
            text += f"  @{info['username']}\n"
        text += f"  /reply_{uid} — ответить\n\n"
    
    await message.answer(text)

@dp.message(Command("reply"))
async def admin_reply_command(message: types.Message, state: FSMContext):
    """Быстрый ответ через команду /reply ID"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /reply ID_ПОЛЬЗОВАТЕЛЯ")
        return
    
    try:
        user_id = int(args[1])
        await state.update_data(replying_to=user_id)
        await state.set_state("admin_replying")
        await message.answer(f"✍️ Режим ответа пользователю {user_id}. Отправьте сообщение...")
    except ValueError:
        await message.answer("❌ Неверный ID пользователя")

# ============ ОБРАБОТКА НЕИЗВЕСТНЫХ ВОПРОСОВ (AI-заглушка) ============
@dp.message(ChatState.automatic)
async def handle_unknown_question(message: types.Message, state: FSMContext):
    """Обработка вопросов, на которые бот не знает ответ"""
    # Здесь можно добавить интеграцию с AI (OpenAI, Anthropic и т.д.)
    # Пока предлагаем связаться с юристом
    
    await message.answer(
        "🤔 <b>Это интересный вопрос!</b>\n\n"
        "Для точного ответа по вашей ситуации лучше проконсультироваться лично.\n\n"
        "👨‍⚖️ <b>Хотите связаться с юристом?</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, связаться", callback_data="call_operator")],
            [InlineKeyboardButton(text="📞 Позвонить", url="tel:+79774232473")],
            [InlineKeyboardButton(text="❌ Нет, спасибо", callback_data="stay_auto")]
        ])
    )

@dp.callback_query(F.data == "call_operator")
async def callback_call_operator(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await call_operator(callback.message, state)

@dp.callback_query(F.data == "stay_auto")
async def callback_stay_auto(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "👌 Понял! Если передумаете — нажмите «Связаться с юристом» в меню."
    )

# ============ WEBHOOK ============
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return web.Response(status=500, text="Ошибка")

async def on_startup(app: web.Application = None):
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")
    
    me = await bot.get_me()
    logger.info(f"🤖 Бот @{me.username} запущен!")

async def on_shutdown(app: web.Application = None):
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("👋 Бот остановлен")

# ============ ВЕБ-СЕРВЕР ============
async def handle_root(request: web.Request):
    return web.Response(
        text="✅ Консуллекс бот работает!\n"
             f"URL: {WEBHOOK_URL}\n"
             "Статус: Активен\n"
             "Функции: Меню + Оператор"
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
