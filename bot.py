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

# ============ НАСТРОЙКА ЛОГИРОВАНИЯ В САМОМ НАЧАЛЕ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============ НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ RENDER ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "717849646")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://consullex-bot.onrender.com")
WEBHOOK_PATH = "/webhook"

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    raise ValueError("❌ BOT_TOKEN не установлен!")
if not WEBHOOK_URL:
    logger.error("❌ WEBHOOK_URL не установлен!")
    raise ValueError("❌ WEBHOOK_URL не установлен!")

# ============ ИНИЦИАЛИЗАЦИЯ ============
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ============ ГЛАВНОЕ МЕНЮ ============
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Оставить заявку")],
            [KeyboardButton(text="⚖️ Услуги"), KeyboardButton(text="💰 Цены")],
            [KeyboardButton(text="📞 Контакты"), KeyboardButton(text="📋 Документы")],
            [KeyboardButton(text="❓ FAQ"), KeyboardButton(text="⭐ Отзывы")]
        ],
        resize_keyboard=True
    )

# ============ ОСНОВНЫЕ КОМАНДЫ ============
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = f"""
👑 <b>Добро пожаловать в Консуллекс!</b>

Здравствуйте, {message.from_user.first_name}!

Я — личный помощник <b>Ивана Серко</b>, частного юриста премиум-класса.

<b>Чем могу помочь:</b>
• 📝 Приму заявку 24/7
• ⚖️ Расскажу об услугах  
• 💰 Сообщу цены
• ❓ Отвечу на вопросы
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
        "/request — оставить заявку\n"
        "/services — услуги\n"
        "/prices — цены\n"
        "/contacts — контакты\n"
        "/documents — документы"
    )

@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong! Бот работает исправно.")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if str(message.from_user.id) != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа")
        return
    await message.answer("🔐 <b>Админ-панель:</b>\n• Статистика\n• Заявки\n• Рассылки")

# ============ МЕНЮ ОБРАБОТЧИКИ ============
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

# ============ WEBHOOK ОБРАБОТЧИК ============
async def handle_webhook(request: web.Request):
    """Обработчик входящих webhook-запросов от Telegram"""
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return web.Response(status=500, text="Ошибка")

async def on_startup(app: web.Application = None):
    """Действия при запуске приложения"""
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    
    # Устанавливаем webhook
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    
    logger.info(f"✅ Webhook установлен: {webhook_url}")
    
    # Информация в консоль
    me = await bot.get_me()
    logger.info(f"🤖 Бот @{me.username} запущен!")

async def on_shutdown(app: web.Application = None):
    """Действия при остановке приложения"""
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("👋 Бот остановлен")

# ============ ВЕБ-СЕРВЕР ============
async def handle_root(request: web.Request):
    """Обработчик для корневого URL"""
    return web.Response(
        text="✅ Консуллекс бот работает!\n"
             f"URL: {WEBHOOK_URL}\n"
             "Статус: Активен\n\n"
             "Бот отвечает на команды и кнопки меню"
    )

def create_app():
    app = web.Application()
    
    # Регистрируем маршруты
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    
    # Регистрируем события запуска/остановки
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    return app

if __name__ == "__main__":
    # Запускаем приложение
    app = create_app()
    port = int(os.getenv("PORT", "10000"))
    
    web.run_app(
        app,
        host="0.0.0.0",
        port=port
    )
