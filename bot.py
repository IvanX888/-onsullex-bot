import os
import sys
import signal
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import contextmanager
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, Contact
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

# ============ ЛОГИРОВАНИЕ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "717849646"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com").strip()

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

logger.info(f"🔧 ADMIN_ID: {ADMIN_ID}")

# ============ SQLite БАЗА ДАННЫХ ============
DB_PATH = "clients.db"

def init_db():
    """Создаёт таблицы, если их нет."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                username TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                total_messages INTEGER DEFAULT 0,
                chats_count INTEGER DEFAULT 0
            )
        """)
        # Индекс для быстрого поиска по banned
        conn.execute("CREATE INDEX IF NOT EXISTS idx_banned ON clients(banned)")

init_db()

@contextmanager
def db_cursor():
    """Контекстный менеджер для работы с БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()

async def update_client_info(user_id: int, name: str = None, username: str = None, increment_messages: bool = False):
    """Создаёт или обновляет запись о клиенте в БД."""
    if user_id == ADMIN_ID:
        return
    now = datetime.now().isoformat()
    with db_cursor() as cur:
        # Проверяем, существует ли запись
        cur.execute("SELECT user_id FROM clients WHERE user_id = ?", (user_id,))
        exists = cur.fetchone()
        if not exists:
            cur.execute("""
                INSERT INTO clients (user_id, name, username, first_seen, last_seen, banned, total_messages)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, (user_id, name or f"User{user_id}", username, now, now, 1 if increment_messages else 0))
            logger.info(f"🆕 Создана запись клиента {user_id} ({name})")
        else:
            # Обновляем last_seen, имя, username
            update_fields = ["last_seen = ?"]
            params = [now]
            if name:
                update_fields.append("name = ?")
                params.append(name)
            if username is not None:
                update_fields.append("username = ?")
                params.append(username)
            if increment_messages:
                update_fields.append("total_messages = total_messages + 1")
            params.append(user_id)
            cur.execute(f"""
                UPDATE clients
                SET {', '.join(update_fields)}
                WHERE user_id = ?
            """, params)

async def is_client_banned(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return False
    with db_cursor() as cur:
        cur.execute("SELECT banned FROM clients WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row["banned"])

async def set_client_ban(user_id: int, ban: bool, reason: str = None):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO clients (user_id, name, username, first_seen, last_seen, banned, ban_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                banned = excluded.banned,
                ban_reason = excluded.ban_reason,
                last_seen = excluded.last_seen
        """, (
            user_id,
            f"User{user_id}",
            None,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            1 if ban else 0,
            reason
        ))

async def get_all_clients():
    with db_cursor() as cur:
        cur.execute("""
            SELECT user_id, name, username, last_seen, banned
            FROM clients
            ORDER BY last_seen DESC
        """)
        rows = cur.fetchall()
        return {row["user_id"]: dict(row) for row in rows}

async def get_client_info(user_id: int):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM clients WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

async def clean_old_clients():
    """Удаляет клиентов, неактивных более 30 дней и не в активных чатах."""
    while True:
        await asyncio.sleep(86400)  # раз в сутки
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        active = await get_all_active_chats()
        placeholders = ','.join('?' * len(active)) if active else 'NULL'
        with db_cursor() as cur:
            # Удаляем клиентов, у которых last_seen < cutoff и не в active
            if active:
                cur.execute(f"""
                    DELETE FROM clients
                    WHERE last_seen < ? AND user_id NOT IN ({placeholders})
                """, (cutoff, *active))
            else:
                cur.execute("DELETE FROM clients WHERE last_seen < ?", (cutoff,))
            deleted = cur.rowcount
            if deleted:
                logger.info(f"🧹 Удалено {deleted} неактивных клиентов")

# ---------- АКТИВНЫЕ ЧАТЫ ----------
active_chats = {}
active_chats_lock = asyncio.Lock()

async def set_active_chat(client_id: int, admin_id: int):
    async with active_chats_lock:
        active_chats[client_id] = admin_id
        logger.debug(f"💬 active_chat установлен: {client_id} -> {admin_id}")

async def remove_active_chat(client_id: int):
    async with active_chats_lock:
        if client_id in active_chats:
            del active_chats[client_id]
            logger.debug(f"💬 active_chat удалён: {client_id}")

async def get_active_chat(client_id: int) -> int | None:
    async with active_chats_lock:
        return active_chats.get(client_id)

async def get_all_active_chats():
    async with active_chats_lock:
        return active_chats.copy()

# ============ FSM СОСТОЯНИЯ ============
class ClientState(StatesGroup):
    menu = State()
    talking_to_lawyer = State()

class AdminState(StatesGroup):
    idle = State()
    talking_to_client = State()
    managing_clients = State()
    waiting_client_id = State()
    waiting_reminder_text = State()

# ============ ИНИЦИАЛИЗАЦИЯ ============
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=storage)

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
def get_fsm_context(user_id: int, chat_id: int = None) -> FSMContext:
    if chat_id is None:
        chat_id = user_id
    key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=chat_id)
    return FSMContext(storage=dp.storage, key=key)

async def safe_send_message(chat_id: int, text: str, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_message(chat_id, text, **kwargs),
            timeout=15.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут отправки сообщения для {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения для {chat_id}: {e}")
        return False

async def safe_send_photo(chat_id: int, photo, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_photo(chat_id, photo, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут отправки фото для {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки фото для {chat_id}: {e}")
        return False

async def safe_send_document(chat_id: int, document, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_document(chat_id, document, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут отправки документа для {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки документа для {chat_id}: {e}")
        return False

async def safe_send_voice(chat_id: int, voice, caption: str = None, **kwargs):
    try:
        await asyncio.wait_for(
            bot.send_voice(chat_id, voice, caption=caption, **kwargs),
            timeout=20.0
        )
        return True
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут отправки голосового для {chat_id}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки голосового для {chat_id}: {e}")
        return False

async def end_chat_for_client(client_id: int, text: str):
    logger.info(f"🔚 Завершение диалога для клиента {client_id}: {text}")
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
    logger.info(f"🔚 Завершение диалога для админа {admin_id}: {text}")
    await state.clear()
    await state.set_state(AdminState.idle)
    await safe_send_message(
        admin_id,
        f"✅ {text}\n\nВы свободны",
        reply_markup=admin_idle_menu(),
        parse_mode=ParseMode.HTML
    )

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
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Управление клиентами")],
            [KeyboardButton(text="🔄 Перезапустить бота")]
        ],
        resize_keyboard=True
    )

def admin_manage_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список клиентов")],
            [KeyboardButton(text="🔒 Заблокировать"), KeyboardButton(text="🔓 Разблокировать")],
            [KeyboardButton(text="📝 Отправить напоминание")],
            [KeyboardButton(text="◀️ Назад в админ-панель")]
        ],
        resize_keyboard=True
    )

def admin_in_chat_menu(client_name: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"❌ Завершить диалог с {client_name}")],
            [KeyboardButton(text="💰 Прайс-лист"), KeyboardButton(text="📞 Запросить контакты")],
            [KeyboardButton(text="❌ Не можем помочь"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔒 Заблокировать этого клиента")]
        ],
        resize_keyboard=True
    )

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

# ============ ГОТОВЫЕ ТЕКСТЫ (АКТУАЛИЗИРОВАНО ПО САЙТУ) ============
BOT_ANSWERS = {
    "привет": "👋 Здравствуйте! Я помогу вам с юридическими вопросами.\n\nВыберите действие в меню ниже ⬇️",
    "здравствуйте": "👋 Добрый день! Готов помочь.\n\nВыберите действие в меню ниже ⬇️",
    "цена": "💰 <b>Стоимость услуг:</b>\n\n• Консультация — от 2 000 ₽\n• Документ — от 4 000 ₽\n• Стартовый пакет (консультация + документ) — от 5 000 ₽\n• Недвижимость — от 15 000 ₽\n• Семейные споры — от 15 000 ₽\n• Наследство — от 10 000 ₽\n• Налоговые споры — от 8 000 ₽\n• Административное право — от 5 000 ₽\n• Трудовые споры — от 12 000 ₽\n• Представительство в суде — от 25 000 ₽\n\nДля точного расчёта нажмите 👨‍⚖️ <b>Связаться с юристом</b>",
    "стоимость": "💰 Консультация от 2 000 ₽. Полный прайс в разделе 💰 Цены. Свяжитесь с юристом для расчёта.",
    "услуги": "⚖️ <b>Мои услуги:</b>\n\n🏛️ <b>Недвижимость</b> (от 15 000 ₽)\n• Проверка квартиры, сопровождение сделки, споры с застройщиком\n\n⚖️ <b>Семейные вопросы</b> (от 15 000 ₽)\n• Развод, раздел имущества, алименты, брачный договор\n\n📜 <b>Наследственные дела</b> (от 10 000 ₽)\n• Вступление в наследство, восстановление сроков, оспаривание\n\n📊 <b>Налоговые споры</b> (от 8 000 ₽)\n• Проверки ФНС, оспаривание штрафов, возврат вычетов\n\n🚗 <b>Административное право</b> (от 5 000 ₽)\n• Штрафы ГИБДД, таможенные споры, обжалование\n\n💼 <b>Трудовые споры</b> (от 12 000 ₽)\n• Незаконное увольнение, задолженность по зарплате\n\n📄 <b>Документы и договоры</b> (от 4 000 ₽)\n• Составление и проверка договоров\n\n⚔️ <b>Представительство в суде</b> (от 25 000 ₽)\n• Иски, жалобы, участие в заседаниях",
    "контакты": "📞 <b>Контакты:</b>\n\n📱 +7 (977) 42-32-473\n📧 333742917@mail.ru\n✈️ Telegram-бот: @ConsulLexbot\n🕐 9:00 — 21:00, ежедневно\n🏛️ г. Москва\n\n<i>Самозанятый юрист. 70% задач решаю онлайн.</i>",
    "телефон": "📞 +7 (977) 42-32-473\n\nРаботаю ежедневно с 9:00 до 21:00",
    "спасибо": "🙏 Пожалуйста! Обращайтесь ещё. Работаю удалённо, но если нужен выезд — обсудим.",
    "до свидания": "👋 До свидания! Если появятся вопросы — пишите, отвечаю в течение суток.",
}

PRICE_LIST = """
<b>💰 Прайс-лист:</b>

<b>Базовые услуги:</b>
• Консультация (30-60 мин) — от 2 000 ₽
• Документ (составление/проверка) — от 4 000 ₽
• Стартовый пакет (консультация + документ) — от 5 000 ₽

<b>Специализация:</b>
• Недвижимость (проверка, сопровождение) — от 15 000 ₽
• Семейные споры (развод, алименты) — от 15 000 ₽
• Наследственные дела — от 10 000 ₽
• Налоговые споры — от 8 000 ₽
• Административное право (штрафы) — от 5 000 ₽
• Трудовые споры — от 12 000 ₽
• Представительство в суде — от 25 000 ₽

<i>Точная стоимость зависит от сложности. Оплата поэтапно или по результату.</i>
"""

ASK_CONTACTS = """
📝 <b>Оставьте ваши контакты</b>

Пожалуйста, напишите:
1. Ваше имя
2. Номер телефона для связи
3. Краткое описание вопроса

Я свяжусь с вами в течение суток.
WhatsApp для срочных вопросов: +7 (977) 42-32-473
"""

CANNOT_HELP = """
❌ <b>К сожалению, я не смогу помочь с этим вопросом.</b>

Возможно, это выходит за рамки моей компетенции. Рекомендую обратиться к узкоспециализированному юристу.

Если передумаете или появится другой вопрос — всегда на связи.
"""

BANNED_MESSAGE = """
⛔ <b>Ваш доступ к юристу временно ограничен.</b>

Пожалуйста, воспользуйтесь другими способами связи:
📞 +7 (977) 42-32-473
📧 333742917@mail.ru

Если вы считаете, что это ошибка, напишите на email.
"""

# ============ ОБРАБОТЧИКИ ============
# ------------------------------------------------------------
# 1. КОМАНДЫ (наивысший приоритет)
# ------------------------------------------------------------
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
        await update_client_info(uid, message.from_user.full_name, message.from_user.username)
        await state.set_state(ClientState.menu)
        await message.answer(
            f"👨‍⚖️ <b>Иван Серко — юрист онлайн</b>\n\n"
            f"Привет, {message.from_user.first_name}!\n\n"
            f"Решаю юридические вопросы удалённо. 70% задач — онлайн, без встреч в офисе. "
            f"Работаю самозанятым, без команды ассистентов — вы общаетесь напрямую со мной.\n\n"
            f"Выберите действие:",
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

@dp.message(Command("debug"), F.from_user.id == ADMIN_ID)
async def cmd_debug(message: Message, state: FSMContext):
    uid = message.from_user.id
    current_state = await state.get_state()
    chats = await get_all_active_chats()
    clients = await get_all_clients()

    debug_text = f"🛠 <b>Debug info</b>\n\n"
    debug_text += f"👑 Админ: {uid}\n"
    debug_text += f"📌 Текущее состояние: {current_state}\n"
    debug_text += f"💬 Активных чатов: {len(chats)}\n"
    for cid, aid in chats.items():
        debug_text += f"   {cid} -> {aid}\n"
    debug_text += f"👥 Всего клиентов: {len(clients)}\n"
    banned = sum(1 for c in clients.values() if c.get("banned"))
    debug_text += f"🔒 Забанено: {banned}\n"

    await message.answer(debug_text, parse_mode=ParseMode.HTML)

# ------------------------------------------------------------
# 2. КЛИЕНТСКИЕ ХЕНДЛЕРЫ
# ------------------------------------------------------------
@dp.message(StateFilter(ClientState.menu), F.text == "📝 Оставить заявку")
async def client_request(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(
        "📞 <b>Заявка:</b>\n\n"
        "📱 +7 (977) 42-32-473 (WhatsApp)\n"
        "✈️ @ConsulLexbot\n"
        "📧 333742917@mail.ru\n\n"
        "⏰ Отвечаю в течение суток, в рабочие дни быстрее.",
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "⚖️ Услуги")
async def client_services(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(BOT_ANSWERS["услуги"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "💰 Цены")
async def client_prices(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(BOT_ANSWERS["цена"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "📞 Контакты")
async def client_contacts(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(BOT_ANSWERS["контакты"], reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

@dp.message(StateFilter(ClientState.menu), F.text == "❓ Частые вопросы")
async def client_faq(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(
        "❓ <b>Частые вопросы:</b>\n\n"
        "<b>Как проходит удалённая работа?</b>\n"
        "Общаемся в мессенджерах, обмен документами — через облако или email. "
        "Подпись — электронная или у нотариуса. 70% задач решается без встреч.\n\n"
        "<b>А если нужен выезд?</b>\n"
        "Если без личного присутствия не обойтись (суд, нотариус) — приеду. "
        "Но сначала оценю, можно ли решить дистанционно.\n\n"
        "<b>Какие гарантии?</b>\n"
        "Оплата поэтапно или по результату. Если после консультации решите, "
        "что помощь не требуется — верну 100% оплаты. Работаю по договору.\n\n"
        "<b>Как быстро отвечаете?</b>\n"
        "В течение суток. В рабочие дни с 9:00 до 21:00. "
        "Для срочных — пишите в WhatsApp.\n\n"
        "Нажмите 👨‍⚖️ <b>Связаться с юристом</b> для консультации.",
        reply_markup=client_main_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(StateFilter(ClientState.menu), F.text == "👨‍⚖️ Связаться с юристом")
async def client_call_lawyer(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user

    await update_client_info(uid, user.full_name, user.username)

    if await is_client_banned(uid):
        await message.answer(BANNED_MESSAGE, reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)
        logger.info(f"⛔ Забаненный клиент {uid} пытался вызвать юриста")
        return

    existing_admin = await get_active_chat(uid)
    if existing_admin:
        logger.info(f"🔄 Клиент {uid} переподключается. Завершаем старый диалог с админом {existing_admin}.")
        admin_state = get_fsm_context(existing_admin)
        await end_chat_for_admin(existing_admin, admin_state, "Клиент начал новый диалог")
        await end_chat_for_client(uid, "Старый диалог завершён (новое обращение)")

    await state.set_state(ClientState.talking_to_lawyer)

    await message.answer(
        "⏳ <b>Соединяю с юристом...</b>\n\n"
        "✅ Иван Серко получил уведомление.\n\n"
        "Опишите ситуацию кратко — я отвечу лично:",
        reply_markup=client_in_chat_menu(),
        parse_mode=ParseMode.HTML
    )

    try:
        # Сначала блокируем клиента, потом отправляем уведомление
        await set_active_chat(uid, ADMIN_ID)
        await safe_send_message(
            ADMIN_ID,
            f"🔔 <b>НОВЫЙ КЛИЕНТ!</b>\n\n"
            f"👤 {user.full_name}\n🆔 <code>{uid}</code>\n📱 @{user.username or 'нет'}\n⏰ {datetime.now().strftime('%H:%M')}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"start_chat:{uid}:{user.full_name}")]
            ]),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✅ Клиент {uid} подключён")
    except Exception as e:
        logger.error(f"❌ Ошибка при вызове юриста: {e}")
        await message.answer("⚠️ Ошибка связи. Позвоните: +7 (977) 42-32-473", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "❌ Завершить разговор с юристом")
async def client_end_chat(message: Message, state: FSMContext):
    uid = message.from_user.id
    await update_client_info(uid, message.from_user.full_name, message.from_user.username)
    admin_id = await get_active_chat(uid)
    if admin_id:
        admin_state = get_fsm_context(admin_id)
        await end_chat_for_admin(admin_id, admin_state, "Клиент завершил диалог")
    await end_chat_for_client(uid, "Разговор завершён")

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.text == "📞 Телефон для связи")
async def client_phone_request(message: Message, state: FSMContext):
    await message.answer("📞 +7 (977) 42-32-473\n🕐 9:00 — 21:00")

@dp.message(StateFilter(ClientState.talking_to_lawyer), F.contact)
async def client_contact(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user
    contact = message.contact

    await update_client_info(uid, user.full_name, user.username, increment_messages=True)

    admin_id = await get_active_chat(uid)
    if not admin_id:
        await message.answer("⚠️ Связь с юристом потеряна.")
        return

    contact_info = f"📞 <b>Контакт от {user.full_name}:</b>\n"
    contact_info += f"Имя: {contact.first_name} {contact.last_name or ''}\n"
    contact_info += f"Номер: {contact.phone_number}\n"
    if contact.user_id:
        contact_info += f"User ID: {contact.user_id}"

    await safe_send_message(admin_id, contact_info, parse_mode=ParseMode.HTML)
    await message.reply("✅ Контакт отправлен юристу")

@dp.message(StateFilter(ClientState.talking_to_lawyer))
async def client_to_lawyer(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = message.from_user

    await update_client_info(uid, user.full_name, user.username, increment_messages=True)

    if await is_client_banned(uid):
        admin_id = await get_active_chat(uid)
        if admin_id:
            admin_state = get_fsm_context(admin_id)
            await end_chat_for_admin(admin_id, admin_state, "Клиент забанен во время диалога")
        await end_chat_for_client(uid, "Диалог завершён (ограничение доступа)")
        await message.answer(BANNED_MESSAGE, reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)
        return

    admin_id = await get_active_chat(uid)
    if not admin_id:
        await message.answer("⚠️ Связь с юристом потеряна. Начните заново.", reply_markup=client_main_menu())
        await state.set_state(ClientState.menu)
        return

    logger.info(f"📤 Сообщение от клиента {uid} доставлено админу {admin_id}")

    admin_state = get_fsm_context(admin_id)
    admin_data = await admin_state.get_data()
    waiting_contacts = admin_data.get('waiting_contacts', False)

    header = f"💬 <b>{user.full_name}</b>"
    if waiting_contacts:
        header += " [📞 КОНТАКТНЫЕ ДАННЫЕ]"
        await admin_state.update_data(waiting_contacts=False)
    header += "\n—\n"

    sent = False
    try:
        if message.text:
            sent = await safe_send_message(admin_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            sent = await safe_send_photo(
                admin_id, message.photo[-1].file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.document:
            sent = await safe_send_document(
                admin_id, message.document.file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.voice:
            await safe_send_message(admin_id, f"{header}\n🎤 Голосовое:", parse_mode=ParseMode.HTML)
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

        if sent:
            logger.info(f"✅ Сообщение от клиента {uid} доставлено админу {admin_id}")
        else:
            logger.warning(f"⚠️ Сообщение от клиента {uid} НЕ доставлено админу {admin_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки клиентом: {e}")
        await message.reply("⚠️ Ошибка отправки")

@dp.message(StateFilter(ClientState.menu), F.contact)
async def client_contact_in_menu(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username, increment_messages=True)
    await message.answer(
        "📞 Получили ваш контакт! Нажмите 👨‍⚖️ Связаться с юристом для консультации.",
        reply_markup=client_main_menu()
    )

@dp.message(StateFilter(ClientState.menu))
async def client_bot_chat(message: Message, state: FSMContext):
    await update_client_info(message.from_user.id, message.from_user.full_name, message.from_user.username, increment_messages=True)
    text = message.text.lower() if message.text else ""
    answer = None
    for key, resp in BOT_ANSWERS.items():
        if key in text:
            answer = resp
            break
    if not answer:
        answer = "🤔 Нажмите 👨‍⚖️ Связаться с юристом для помощи"
    await message.answer(answer, reply_markup=client_main_menu(), parse_mode=ParseMode.HTML)

# ------------------------------------------------------------
# 3. АДМИН: ДИАЛОГ С КЛИЕНТОМ (callback)
# ------------------------------------------------------------
@dp.callback_query(F.data.startswith("start_chat:"))
async def admin_start_chat(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    logger.info(f"📞 Админ {callback.from_user.id} нажал 'Ответить'")

    parts = callback.data.split(":")
    client_id = int(parts[1])
    client_name = parts[2] if len(parts) > 2 else "Клиент"

    # Обновляем информацию о клиенте
    await update_client_info(client_id, client_name, None)

    # ЗАЩИТА ОТ ПЕРЕКЛЮЧЕНИЯ МЕЖДУ КЛИЕНТАМИ
    current_state = await state.get_state()
    if current_state == AdminState.talking_to_client:
        current_data = await state.get_data()
        current_client = current_data.get('talking_to')
        if current_client and current_client != client_id:
            await callback.answer(
                f"⚠️ Вы уже в чате с {current_data.get('client_name', 'Клиент')} (ID: {current_client})!\n"
                f"Завершите текущий диалог перед ответом новому клиенту.",
                show_alert=True
            )
            return

    # Проверка бана
    if await is_client_banned(client_id):
        await callback.answer("⛔ Клиент забанен, невозможно начать диалог.", show_alert=True)
        return

    # Проверка, не занят ли клиент другим админом
    existing_admin = await get_active_chat(client_id)
    if existing_admin and existing_admin != callback.from_user.id:
        logger.warning(f"⚠️ Админ {callback.from_user.id} пытался подключиться к клиенту {client_id}, но он уже в чате с {existing_admin}")
        await callback.answer("⚠️ Клиент уже находится в активном чате с другим админом.", show_alert=True)
        return

    # ВОССТАНОВЛЕНИЕ ДИАЛОГА (если клиент уже в active_chats с этим админом, но состояние сброшено)
    if existing_admin == callback.from_user.id:
        current_state = await state.get_state()
        if current_state != AdminState.talking_to_client:
            logger.info(f"🔄 Восстановление диалога для админа {callback.from_user.id} с клиентом {client_id}")
            await state.set_state(AdminState.talking_to_client)
            await state.update_data(talking_to=client_id, client_name=client_name, waiting_contacts=False)
            await callback.message.answer(
                f"🔄 <b>Диалог восстановлен</b>\n\nОбщение с <b>{client_name}</b>\nID: <code>{client_id}</code>",
                reply_markup=admin_in_chat_menu(client_name),
                parse_mode=ParseMode.HTML
            )
            await callback.answer("✅ Диалог восстановлен", show_alert=False)
        else:
            await callback.answer("✅ Вы уже в чате с этим клиентом.", show_alert=True)
        return

    # Новый диалог
    await state.set_state(AdminState.talking_to_client)
    await state.update_data(talking_to=client_id, client_name=client_name, waiting_contacts=False)
    await set_active_chat(client_id, callback.from_user.id)

    await callback.message.answer(
        f"✍️ Общение с <b>{client_name}</b>\nID: <code>{client_id}</code>",
        reply_markup=admin_in_chat_menu(client_name),
        parse_mode=ParseMode.HTML
    )

    await safe_send_message(
        client_id,
        "👨‍⚖️ <b>Юрист подключился!</b>\n\nИван Серко на связи. Опишите вашу ситуацию.",
        parse_mode=ParseMode.HTML
    )

    await callback.answer("✅ Подключены")

# ------------------------------------------------------------
# 4. АДМИН: ГОРЯЧИЕ КЛАВИШИ В ДИАЛОГЕ (приоритет выше общего)
# ------------------------------------------------------------
@dp.message(StateFilter(AdminState.talking_to_client), F.text == "💰 Прайс-лист")
async def admin_send_price_list(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logger.info(f"💰 Админ нажал: {message.text}")
    data = await state.get_data()
    client_id = data.get('talking_to')
    if not client_id:
        await message.answer("⚠️ Нет активного клиента")
        return

    if not await get_active_chat(client_id):
        await message.answer("⚠️ Клиент отключился или завершил диалог")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return

    sent = await safe_send_message(client_id, PRICE_LIST, parse_mode=ParseMode.HTML)
    if sent:
        await message.answer("✅ Прайс-лист отправлен клиенту")
        logger.info(f"📤 Админ отправил прайс-лист клиенту {client_id}")
    else:
        await message.answer("❌ Не удалось отправить прайс-лист")

@dp.message(StateFilter(AdminState.talking_to_client), F.text == "📞 Запросить контакты")
async def admin_ask_contacts(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logger.info(f"📞 Админ нажал: {message.text}")
    data = await state.get_data()
    client_id = data.get('talking_to')
    if not client_id:
        await message.answer("⚠️ Нет активного клиента")
        return

    if not await get_active_chat(client_id):
        await message.answer("⚠️ Клиент отключился или завершил диалог")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return

    await state.update_data(waiting_contacts=True)
    sent = await safe_send_message(client_id, ASK_CONTACTS, parse_mode=ParseMode.HTML)
    if sent:
        await message.answer("✅ Запрос контактов отправлен клиенту")
        logger.info(f"📤 Админ запросил контакты у клиента {client_id}")
    else:
        await message.answer("❌ Не удалось отправить запрос")

@dp.message(StateFilter(AdminState.talking_to_client), F.text == "❌ Не можем помочь")
async def admin_cannot_help(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logger.info(f"❌ Админ нажал: {message.text}")
    data = await state.get_data()
    client_id = data.get('talking_to')
    if not client_id:
        await message.answer("⚠️ Нет активного клиента")
        return

    if not await get_active_chat(client_id):
        await message.answer("⚠️ Клиент отключился или завершил диалог")
        await state.clear()
        await state.set_state(AdminState.idle)
        await message.answer("Вы свободны", reply_markup=admin_idle_menu())
        return

    sent = await safe_send_message(client_id, CANNOT_HELP, parse_mode=ParseMode.HTML)
    if sent:
        await message.answer("✅ Уведомление об отказе отправлено клиенту")
        logger.info(f"📤 Админ отказал клиенту {client_id}")
    else:
        await message.answer("❌ Не удалось отправить уведомление")

@dp.message(StateFilter(AdminState.talking_to_client), F.text == "🔒 Заблокировать этого клиента")
async def admin_ban_client_from_chat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logger.info(f"🔒 Админ нажал: {message.text}")
    data = await state.get_data()
    client_id = data.get('talking_to')
    client_name = data.get('client_name', 'Клиент')
    if not client_id:
        await message.answer("⚠️ Нет активного клиента")
        return

    await set_client_ban(client_id, True, reason="Заблокирован админом во время диалога")
    logger.info(f"⛔ Админ {message.from_user.id} заблокировал клиента {client_id}")

    await end_chat_for_client(client_id, "Админ заблокировал доступ к юристу")
    await end_chat_for_admin(message.from_user.id, state, f"Клиент {client_name} заблокирован и диалог завершён")
    await message.answer(f"🔒 Клиент {client_name} (ID: {client_id}) заблокирован.")

@dp.message(StateFilter(AdminState.talking_to_client), F.text.startswith("❌ Завершить диалог с"))
async def admin_end_chat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    logger.info(f"❌ Админ завершает диалог: {message.text}")
    data = await state.get_data()
    client_id = data.get('talking_to')
    client_name = data.get('client_name', 'Клиент')
    if client_id:
        await end_chat_for_client(client_id, "Юрист завершил консультацию")
        await end_chat_for_admin(message.from_user.id, state, f"Диалог с {client_name} завершён")

# СТАТИСТИКА В ДИАЛОГЕ
@dp.message(StateFilter(AdminState.talking_to_client), F.text == "📊 Статистика")
async def admin_stats_in_chat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    chats = await get_all_active_chats()
    count = len(chats)
    clients_list = list(chats.keys())
    total_clients = len(await get_all_clients())
    banned_clients = 0
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM clients WHERE banned = 1")
        row = cur.fetchone()
        banned_clients = row["cnt"] if row else 0

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего клиентов: {total_clients}\n"
        f"🔒 Заблокировано: {banned_clients}\n"
        f"💬 Активных диалогов: {count}\n"
        f"🆔 Активные клиенты: {clients_list if clients_list else 'нет'}",
        parse_mode=ParseMode.HTML
    )

# БЛОКИРОВКА КНОПОК УПРАВЛЕНИЯ В ДИАЛОГЕ
@dp.message(StateFilter(AdminState.talking_to_client), F.text.in_(["👥 Управление клиентами", "🔄 Перезапустить бота"]))
async def admin_blocked_in_chat(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "⚠️ <b>Сначала завершите диалог с клиентом!</b>\n\n"
        "Используйте кнопку ❌ Завершить диалог",
        parse_mode=ParseMode.HTML
    )

# ------------------------------------------------------------
# 5. АДМИН: ОБЩИЙ ОБРАБОТЧИК СООБЩЕНИЙ В ДИАЛОГЕ (текст от админа клиенту)
# ------------------------------------------------------------
@dp.message(StateFilter(AdminState.talking_to_client))
async def admin_to_client(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
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

    # Обновляем last_seen клиента
    await update_client_info(client_id, None, None, increment_messages=False)

    header = "👨‍⚖️ <b>Иван Серко:</b>\n\n"
    sent = False
    try:
        if message.text:
            sent = await safe_send_message(client_id, header + message.text, parse_mode=ParseMode.HTML)
        elif message.photo:
            sent = await safe_send_photo(
                client_id, message.photo[-1].file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.document:
            sent = await safe_send_document(
                client_id, message.document.file_id,
                caption=header + (message.caption or ""),
                parse_mode=ParseMode.HTML
            )
        elif message.voice:
            await safe_send_message(client_id, header, parse_mode=ParseMode.HTML)
            sent = await safe_send_voice(client_id, message.voice.file_id, parse_mode=ParseMode.HTML)
        else:
            await message.answer("❌ Неподдерживаемый тип")
            return

        if sent:
            await message.answer("✅ Отправлено")
            logger.info(f"📤 Админ -> Клиент {client_id}")
        else:
            await message.answer("⚠️ Ошибка отправки (возможно, клиент недоступен)")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки админом: {e}")
        await message.answer("❌ Ошибка отправки")

# ------------------------------------------------------------
# 6. АДМИН: КНОПКИ В СОСТОЯНИИ IDLE (приоритет выше заглушки)
# ------------------------------------------------------------
@dp.message(F.from_user.id == ADMIN_ID, F.text == "📊 Статистика", StateFilter(AdminState.idle))
async def admin_stats_idle(message: Message, state: FSMContext):
    chats = await get_all_active_chats()
    count = len(chats)
    clients_list = list(chats.keys())
    total_clients = len(await get_all_clients())
    banned_clients = 0
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM clients WHERE banned = 1")
        row = cur.fetchone()
        banned_clients = row["cnt"] if row else 0

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего клиентов: {total_clients}\n"
        f"🔒 Заблокировано: {banned_clients}\n"
        f"💬 Активных диалогов: {count}\n"
        f"🆔 Активные клиенты: {clients_list if clients_list else 'нет'}",
        parse_mode=ParseMode.HTML
    )

@dp.message(F.from_user.id == ADMIN_ID, F.text == "👥 Управление клиентами", StateFilter(AdminState.idle))
async def admin_manage_clients_entry(message: Message, state: FSMContext):
    await state.set_state(AdminState.managing_clients)
    await message.answer(
        "👥 <b>Управление клиентами</b>\n\nВыберите действие:",
        reply_markup=admin_manage_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(F.from_user.id == ADMIN_ID, F.text == "🔄 Перезапустить бота", StateFilter(AdminState.idle))
async def admin_restart(message: Message, state: FSMContext):
    await message.answer("♻️ Перезапуск...")
    logger.info(f"🔄 Админ {ADMIN_ID} инициировал перезапуск бота")
    os.kill(os.getpid(), signal.SIGTERM)

# ------------------------------------------------------------
# 7. АДМИН: УПРАВЛЕНИЕ КЛИЕНТАМИ (ОЖИДАНИЕ ID, ТЕКСТА НАПОМИНАНИЯ)
# ------------------------------------------------------------
@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.managing_clients), F.text == "◀️ Назад в админ-панель")
async def admin_manage_back(message: Message, state: FSMContext):
    await state.set_state(AdminState.idle)
    await message.answer(
        "🔐 <b>Админ-панель</b>\n\nВы свободны.",
        reply_markup=admin_idle_menu(),
        parse_mode=ParseMode.HTML
    )

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.managing_clients), F.text == "📋 Список клиентов")
async def admin_list_clients(message: Message, state: FSMContext):
    clients = await get_all_clients()
    if not clients:
        await message.answer("📭 Нет ни одного клиента.")
        return
    lines = ["📋 <b>Все клиенты:</b>\n"]
    for uid, info in clients.items():
        banned = "🔒" if info.get("banned") else "✅"
        name = info.get("name", "Unknown")
        username = info.get("username")
        username_str = f" @{username}" if username else ""
        last_seen = info.get("last_seen", "никогда")[5:16]
        lines.append(f"{banned} <code>{uid}</code> - {name}{username_str}\n    👁 Посл.: {last_seen}")
        if len(lines) > 30:
            lines.append("... и ещё несколько")
            break
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.managing_clients), F.text == "🔒 Заблокировать")
async def admin_ban_client_request(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_client_id)
    await state.update_data(ban_action="ban", reminder_action=False, reminder_target=None)
    await message.answer(
        "🔒 Введите ID клиента, которого нужно заблокировать:\n"
        "(можно скопировать из списка клиентов)"
    )

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.managing_clients), F.text == "🔓 Разблокировать")
async def admin_unban_client_request(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_client_id)
    await state.update_data(ban_action="unban", reminder_action=False, reminder_target=None)
    await message.answer("🔓 Введите ID клиента, которого нужно разблокировать:")

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.managing_clients), F.text == "📝 Отправить напоминание")
async def admin_remind_client_request(message: Message, state: FSMContext):
    await state.set_state(AdminState.waiting_client_id)
    await state.update_data(reminder_action=True, ban_action=None)
    await message.answer("📝 Введите ID клиента, которому нужно отправить напоминание:")

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.waiting_client_id))
async def admin_process_client_id(message: Message, state: FSMContext):
    if not message.text or message.text.startswith('/'):
        return
    # Игнорируем кнопки
    if message.text in ["◀️ Назад в админ-панель", "📋 Список клиентов", "🔒 Заблокировать", "🔓 Разблокировать", "📝 Отправить напоминание"]:
        return

    data = await state.get_data()
    ban_action = data.get('ban_action')
    reminder_action = data.get('reminder_action')

    try:
        client_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число.")
        return

    client_info = await get_client_info(client_id)
    if not client_info:
        await message.answer(f"❌ Клиент с ID <code>{client_id}</code> не найден в базе.", parse_mode=ParseMode.HTML)
        await state.set_state(AdminState.managing_clients)
        await state.update_data(ban_action=None, reminder_action=False)
        return

    if ban_action:
        if ban_action == "ban":
            await set_client_ban(client_id, True, reason="Заблокирован админом через меню")
            await message.answer(f"🔒 Клиент <code>{client_id}</code> заблокирован.", parse_mode=ParseMode.HTML)
            logger.info(f"⛔ Админ {message.from_user.id} заблокировал клиента {client_id}")
            admin_in_chat = await get_active_chat(client_id)
            if admin_in_chat:
                admin_state = get_fsm_context(admin_in_chat)
                await end_chat_for_admin(admin_in_chat, admin_state, "Клиент заблокирован")
                await end_chat_for_client(client_id, "Доступ к юристу заблокирован")
        elif ban_action == "unban":
            await set_client_ban(client_id, False)
            await message.answer(f"🔓 Клиент <code>{client_id}</code> разблокирован.", parse_mode=ParseMode.HTML)
            logger.info(f"✅ Админ {message.from_user.id} разблокировал клиента {client_id}")
        await state.set_state(AdminState.managing_clients)
        await state.update_data(ban_action=None, reminder_action=False)
        return

    elif reminder_action:
        await state.set_state(AdminState.waiting_reminder_text)
        await state.update_data(reminder_target=client_id, reminder_action=False)
        await message.answer(f"📝 Введите текст напоминания для клиента <code>{client_id}</code>:", parse_mode=ParseMode.HTML)
        return

@dp.message(F.from_user.id == ADMIN_ID, StateFilter(AdminState.waiting_reminder_text))
async def admin_send_reminder_text(message: Message, state: FSMContext):
    if not message.text or message.text.startswith('/'):
        return
    if message.text in ["◀️ Назад в админ-панель", "📋 Список клиентов", "🔒 Заблокировать", "🔓 Разблокировать", "📝 Отправить напоминание"]:
        return

    data = await state.get_data()
    client_id = data.get('reminder_target')
    if not client_id:
        await state.set_state(AdminState.managing_clients)
        return

    reminder_text = message.text.strip()
    if not reminder_text:
        await message.answer("❌ Текст не может быть пустым.")
        return

    sent = await safe_send_message(
        client_id,
        f"📌 <b>Напоминание от администратора:</b>\n\n{reminder_text}",
        parse_mode=ParseMode.HTML
    )
    if sent:
        await message.answer(f"✅ Напоминание отправлено клиенту <code>{client_id}</code>.", parse_mode=ParseMode.HTML)
        logger.info(f"📨 Админ отправил напоминание клиенту {client_id}")
    else:
        await message.answer(f"❌ Не удалось отправить напоминание клиенту <code>{client_id}</code>.", parse_mode=ParseMode.HTML)

    await state.set_state(AdminState.managing_clients)
    await state.update_data(reminder_target=None)

# ------------------------------------------------------------
# 8. АДМИН: ЗАГЛУШКА ДЛЯ СОСТОЯНИЯ IDLE (самый низкий приоритет)
# ------------------------------------------------------------
@dp.message(StateFilter(AdminState.idle))
async def admin_idle(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.startswith('/'):
        return
    await message.answer("ℹ️ Вы свободны. Ждите клиента или нажмите /start", reply_markup=admin_idle_menu())

# ============ WEBHOOK ============
async def handle_webhook(request: web.Request):
    """Синхронная обработка вебхука с таймаутом 55 секунд."""
    try:
        data = await request.json()
        logger.debug(f"📩 Webhook received: {data.get('update_id', 'unknown')}")
        await asyncio.wait_for(dp.feed_raw_update(bot, data), timeout=55.0)
        return web.Response(text="OK", status=200)
    except asyncio.TimeoutError:
        logger.error("⏰ Webhook processing timeout (55s)")
        return web.Response(text="OK", status=200)
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return web.Response(text="Error", status=200)

async def health(request: web.Request):
    return web.Response(text="OK")

async def root(request: web.Request):
    return web.Response(text=f"Bot OK. Admin: {ADMIN_ID}")

# ============ MAIN ============
async def main():
    port = int(os.getenv("PORT", "10000"))

    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_post("/webhook", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🚀 Сервер запущен на порту {port}")

    # Фоновая очистка неактивных клиентов
    asyncio.create_task(clean_old_clients())

    webhook_url = f"{WEBHOOK_URL}/webhook"
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
