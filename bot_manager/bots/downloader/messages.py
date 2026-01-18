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
CAPTION = "@SaveNinja_bot"

# ============ Дефолтные сообщения (fallback) ============

DEFAULTS = {
    "start": """
<b>👋 Привет! Я SaveNinja</b>

Отправь мне ссылку и я скачаю для тебя:
• 🎬 <b>Видео</b> (автопроигрывание)
• 🎵 <b>Аудио MP3</b> (320 kbps)

<b>Что поддерживается?</b>

📸 <b>Instagram</b>
Фото, видео, карусели, истории, актуальное

📌 <b>Pinterest</b>
Фото и видео

🎵 <b>TikTok</b>
Видео без водяного знака

▶️ <b>YouTube Shorts</b>
Короткие видео

Просто отправь ссылку!
""".strip(),

    "help": """
<b>❓ Помощь</b>

<b>Как пользоваться:</b>
1. Скопируй ссылку на видео/фото
2. Отправь её мне
3. Получи медиа + аудио!

<b>Примеры ссылок:</b>
• <code>https://www.instagram.com/p/...</code>
• <code>https://www.instagram.com/reel/...</code>
• <code>https://www.instagram.com/stories/...</code>
• <code>https://vm.tiktok.com/...</code>
• <code>https://youtube.com/shorts/...</code>
• <code>https://pin.it/...</code>
• <code>https://pinterest.com/pin/...</code>

<b>Ограничения:</b>
• Максимальный размер: 50MB
• Приватный контент не поддерживается
""".strip(),

    "downloading": "⏳ Скачиваю видео...",
    "processing": "🎬 Обрабатываю видео...",
    "compressing": "📦 Сжимаю под формат Telegram...",
    "uploading": "📤 Отправляю...",
    "extracting_audio": "🎵 Извлекаю аудио...",
    "success": "✅ Готово!",
    "rate_limit_user": "⏳ Подожди, у тебя уже качается видео...",
    "downloading_large": "⏳ Скачиваю большое видео...",
    "sent_as_document": "Видео слишком большое для автопроигрывания, отправлено как файл",
    "error_not_found": "❌ Видео не найдено. Проверь ссылку.",
    "error_timeout": "⏱ Превышено время ожидания. Попробуй позже.",
    "error_too_large": "📦 Файл слишком большой (>50MB). Telegram не позволяет.",
    "error_unknown": "❌ Произошла ошибка. Попробуй позже.",
    "error_invalid_url": """
⛔️ <b>Ссылка не поддерживается!</b>

<b>Что поддерживается?</b>

📸 <b>Instagram</b>
Фото, видео, карусели, истории, актуальное

📌 <b>Pinterest</b>
Фото и видео

🎵 <b>TikTok</b>
Видео без водяного знака

▶️ <b>YouTube Shorts</b>
Короткие видео
""".strip(),
    "error_private": "🔒 Это приватный контент. Доступ ограничен.",
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
    """
    # Сначала из кэша БД
    if _cache_loaded and key in _messages_cache:
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
