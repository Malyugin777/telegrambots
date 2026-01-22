"""
Текстовые сообщения бота SaveNinja
Загружаются из БД с fallback на дефолтные значения
Кэш автоматически обновляется каждые 60 секунд
"""
import logging
import time
import asyncio
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Bot ID для SaveNinja (из таблицы bots)
BOT_ID = 1

# TTL кэша в секундах
CACHE_TTL = 60

# Подпись под медиа (не хранится в БД)
CAPTION = "📥 Скачано через @SaveNinja_bot"

# ============ Дефолтные сообщения (fallback) ============

DEFAULTS = {
    "start": """<b>👋 Привет! Я SaveNinja</b>

Отправь ссылку — я скачаю и пришлю:
• 🎬 <b>Видео</b>
• 🎵 <b>Аудио MP3</b> (320 kbps)

<b>Поддерживаю:</b>

📸 <b>Instagram</b>
Посты, Reels, карусели, истории*

🎵 <b>TikTok</b>
Видео (стараюсь без водяных знаков)

📌 <b>Pinterest</b>
Фото и видео

▶️ <b>YouTube</b>
Shorts и обычные видео (до 2GB)

Просто пришли ссылку 👇

<i>* Истории иногда недоступны (24ч/приватность/удалено).</i>""",

    "help": """<b>❓ Помощь</b>

<b>Как пользоваться:</b>
1) Скопируй ссылку
2) Отправь её мне
3) Получи медиа (и при желании — MP3)

<b>Примеры ссылок:</b>
• <code>https://www.instagram.com/p/...</code>
• <code>https://www.instagram.com/reel/...</code>
• <code>https://www.instagram.com/stories/...</code>
• <code>https://vm.tiktok.com/...</code>
• <code>https://youtube.com/shorts/...</code>
• <code>https://www.youtube.com/watch?v=...</code>
• <code>https://pin.it/...</code>
• <code>https://pinterest.com/pin/...</code>

<b>Ограничения:</b>
• Максимальный размер видео: до 2GB
• Приватный контент может не скачаться""",

    "downloading": "⏳ Скачиваю...",
    "processing": "🎬 Обрабатываю...",
    "compressing": "📦 Оптимизирую под Telegram...",
    "uploading": "📤 Отправляю в Telegram...",
    "extracting_audio": "🎵 Делаю MP3...",
    "success": "✅ Готово!",
    "rate_limit_user": "⏳ Подожди, у тебя уже идёт скачивание...",
    "downloading_large": "⏳ Скачиваю большое видео… это может занять пару минут.",
    "error_not_found": "❌ Не нашёл медиа по этой ссылке. Проверь, что она правильная.",
    "error_timeout": "⏱ Не успел скачать/отправить. Попробуй ещё раз чуть позже.",
    "error_too_large": "📦 Файл слишком большой (>2GB). Telegram такое не пропускает.",
    "error_too_large_2gb": "❌ Видео слишком большое (>2GB).",
    "error_unknown": "❌ Что-то пошло не так. Попробуй позже.",
    "error_unavailable": "❌ Контент недоступен (удалён/скрыт).",
    "error_region": "🌍 Контент недоступен в этом регионе.",
    "error_api": "⚠️ Внешний сервис временно глючит. Попробуй позже.",
    "error_connection": "📡 Проблема с соединением. Попробуй позже.",
    "error_processing": "⚙️ Не смог обработать видео. Попробуй другую ссылку или позже.",
    "error_upload": "📤 Не удалось отправить файл в Telegram. Попробуй ещё раз.",
    "error_transport": "📡 Telegram разорвал соединение при загрузке. Попробуй ещё раз.",
    "error_invalid_url": """⛔️ <b>Ссылка не поддерживается!</b>

<b>Я умею:</b>

📸 <b>Instagram</b>
Посты, Reels, карусели, истории

🎵 <b>TikTok</b>
Видео

▶️ <b>YouTube</b>
Shorts и обычные видео

📌 <b>Pinterest</b>
Фото и видео""",
    "error_private": "🔒 Контент приватный — скачать не получится.",
    "error_story": """📖 <b>История недоступна</b>

Возможные причины:
• История истекла (24 часа)
• Аккаунт приватный
• История удалена автором

💡 Попробуй скачать посты или Reels этого автора.""",
    # Прогресс и fallback
    "trying_fallback": "⏳ Переключаюсь на резервный способ…",
    "progress_with_size": "⏳ Скачиваю... {minutes} мин, {downloaded_mb} MB / {total_mb} MB",
    "progress_no_size": "⏳ Скачиваю... {minutes} мин, подожди",
    "unsupported_hint": "Поддерживаю: Instagram, TikTok, YouTube (Shorts/видео), Pinterest",
}

# ============ Кэш сообщений из БД ============

_messages_cache: dict[str, str] = {}
_cache_loaded: bool = False
_cache_loaded_at: float = 0  # timestamp последней загрузки
_refresh_task: Optional[asyncio.Task] = None


async def load_messages_from_db(session) -> dict[str, str]:
    """Загрузить сообщения из БД."""
    global _messages_cache, _cache_loaded, _cache_loaded_at

    try:
        from shared.database.models import BotMessage
        from sqlalchemy import select

        result = await session.execute(
            select(BotMessage).where(
                BotMessage.bot_id == BOT_ID,
                BotMessage.is_active == True
            )
        )
        messages = result.scalars().all()

        _messages_cache = {msg.message_key: msg.text_ru for msg in messages}
        _cache_loaded = True
        _cache_loaded_at = time.time()

        logger.info(f"Loaded {len(_messages_cache)} messages from DB for bot_id={BOT_ID}")
        return _messages_cache

    except Exception as e:
        logger.warning(f"Failed to load messages from DB: {e}, using defaults")
        _cache_loaded = False
        return {}


def reload_messages_cache():
    """Сбросить кэш (вызывать при обновлении через админку)."""
    global _messages_cache, _cache_loaded, _cache_loaded_at
    _messages_cache = {}
    _cache_loaded = False
    _cache_loaded_at = 0
    logger.info("Messages cache cleared")


async def _refresh_cache_loop():
    """Фоновая задача: перезагружает кэш каждые CACHE_TTL секунд."""
    from shared.database import AsyncSessionLocal

    while True:
        await asyncio.sleep(CACHE_TTL)
        try:
            async with AsyncSessionLocal() as session:
                await load_messages_from_db(session)
                logger.debug(f"Cache auto-refreshed (TTL={CACHE_TTL}s)")
        except Exception as e:
            logger.warning(f"Cache refresh failed: {e}")


def start_cache_refresh_task():
    """Запустить фоновую задачу обновления кэша."""
    global _refresh_task
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.create_task(_refresh_cache_loop())
        logger.info(f"Started cache refresh task (TTL={CACHE_TTL}s)")


def stop_cache_refresh_task():
    """Остановить фоновую задачу обновления кэша."""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
        logger.info("Stopped cache refresh task")


def get_message(key: str, lang: str = "ru") -> str:
    """
    Получить сообщение по ключу.
    Сначала ищет в кэше БД, потом в дефолтах.
    Проверяет TTL кэша - если протух, использует дефолты.
    """
    # Проверяем что кэш загружен и не протух
    cache_age = time.time() - _cache_loaded_at if _cache_loaded_at > 0 else float('inf')
    cache_is_valid = _cache_loaded and cache_age < CACHE_TTL * 2  # 2x TTL для запаса

    if not cache_is_valid and _cache_loaded:
        logger.warning(f"Messages cache expired (age={cache_age:.0f}s, TTL={CACHE_TTL}s), using defaults")

    # Сначала из кэша БД (если не протух)
    if cache_is_valid and key in _messages_cache:
        return _messages_cache[key]

    # Fallback на дефолты
    return DEFAULTS.get(key, f"[Message '{key}' not found]")


# ============ Функции для использования в хендлерах ============

def get_start_message() -> str:
    return get_message("start")

def get_help_message() -> str:
    return get_message("help")

def get_downloading_message() -> str:
    return get_message("downloading")

def get_processing_message() -> str:
    return get_message("processing")

def get_compressing_message() -> str:
    return get_message("compressing")

def get_uploading_message() -> str:
    return get_message("uploading")

def get_sending_message() -> str:
    """Deprecated: используй get_uploading_message()"""
    return get_message("uploading")

def get_extracting_audio_message() -> str:
    return get_message("extracting_audio")

def get_success_message() -> str:
    return get_message("success")

def get_rate_limit_message() -> str:
    return get_message("rate_limit_user")

def get_error_message(error_type: str = "unknown") -> str:
    """Получить сообщение об ошибке по типу."""
    key = f"error_{error_type}"
    return get_message(key)

def get_unsupported_url_message() -> str:
    return get_message("error_invalid_url")


# ============ Алиасы для обратной совместимости (deprecated) ============
# Эти константы будут использовать дефолты, пока кэш не загружен

STATUS_DOWNLOADING = DEFAULTS["downloading"]
STATUS_EXTRACTING_AUDIO = DEFAULTS["extracting_audio"]
START_MESSAGE = DEFAULTS["start"]
HELP_MESSAGE = DEFAULTS["help"]
UNSUPPORTED_URL_MESSAGE = DEFAULTS["error_invalid_url"]
