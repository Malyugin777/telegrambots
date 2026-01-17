import os
import re
import asyncio
import logging
from pathlib import Path
from aiogram import Router, types, F
from aiogram.types import FSInputFile
import yt_dlp

router = Router()
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Улучшенная регулярка
URL_PATTERN = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?"  # поддомены типа ru. www. m.
    r"(?:tiktok\.com|vm\.tiktok\.com|"
    r"instagram\.com|"
    r"youtube\.com/shorts|youtu\.be|"
    r"pinterest\.[a-z.]+|pin\.it)"
    r"[^\s]*",
    re.IGNORECASE
)

CAPTION = "Скачано через @SaveNinja_bot"


def get_yt_dlp_opts(output_path: str) -> dict:
    return {
        "outtmpl": output_path,
        # Формат: лучшее видео до 50MB, с предпочтением mp4
        "format": (
            "best[ext=mp4][filesize<50M]/"
            "best[filesize<50M]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/best"
        ),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "http_chunk_size": 10485760,
        "nocheckcertificate": True,
        "geo_bypass": True,
        # YouTube: используем android и web клиенты
        "extractor_args": {
            "youtube": {"player_client": ["android", "web"]},
            "tiktok": {"api_hostname": "api22-normal-c-useast2a.tiktokv.com"},
        },
        # User-Agent для обхода блокировок
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    }


async def download_video(url: str, chat_id: int) -> tuple[str | None, str | None]:
    """
    Скачивает видео по URL.
    Возвращает (путь_к_файлу, ошибка) - одно из значений всегда None.
    """
    output_path = str(DOWNLOAD_DIR / f"{chat_id}_%(id)s.%(ext)s")
    opts = get_yt_dlp_opts(output_path)

    try:
        loop = asyncio.get_event_loop()

        def _download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None, "Не удалось получить информацию о видео"
                return ydl.prepare_filename(info), None

        file_path, error = await asyncio.wait_for(
            loop.run_in_executor(None, _download),
            timeout=60
        )
        if error:
            return None, error
        return file_path, None

    except asyncio.TimeoutError:
        logger.error(f"Download timeout for {url}")
        return None, "Таймаут загрузки (60 сек)"
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        logger.error(f"yt-dlp DownloadError for {url}: {error_msg}")
        # Форматируем ошибку для пользователя
        if "private" in error_msg.lower():
            return None, "Видео приватное"
        elif "unavailable" in error_msg.lower() or "not available" in error_msg.lower():
            return None, "Видео недоступно"
        elif "age" in error_msg.lower():
            return None, "Видео с ограничением по возрасту"
        elif "login" in error_msg.lower() or "sign in" in error_msg.lower():
            return None, "Требуется авторизация"
        elif "404" in error_msg or "not found" in error_msg.lower():
            return None, "Видео не найдено"
        else:
            return None, error_msg[:100]
    except Exception as e:
        logger.exception(f"Download error for {url}: {e}")
        return None, str(e)[:100]


@router.message(F.text.regexp(URL_PATTERN))
async def handle_url(message: types.Message):
    match = URL_PATTERN.search(message.text)
    if not match:
        return
    url = match.group()

    logger.info(f"Download request: user={message.from_user.id}, url={url}")
    status_msg = await message.answer("⏳ Скачиваю видео...")

    try:
        file_path, error = await download_video(url, message.chat.id)

        if error:
            logger.warning(f"Download failed: user={message.from_user.id}, error={error}")
            await status_msg.edit_text(f"❌ {error}")
            return

        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            logger.info(f"Downloaded: {file_path}, size={file_size}")

            if file_size > 50 * 1024 * 1024:
                await status_msg.edit_text("❌ Файл слишком большой (>50MB)")
                os.remove(file_path)
                return

            await status_msg.edit_text("📤 Отправляю...")

            video = FSInputFile(file_path)
            await message.answer_video(video, caption=CAPTION)
            await status_msg.delete()

            logger.info(f"Sent video to user={message.from_user.id}")

            try:
                os.remove(file_path)
            except:
                pass
        else:
            await status_msg.edit_text("❌ Не удалось скачать. Попробуй другую ссылку.")

    except Exception as e:
        logger.exception(f"Handler error: {e}")
        try:
            await status_msg.edit_text(f"❌ Ошибка: {str(e)[:50]}")
        except:
            pass


@router.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/"):
        return
    await message.answer(
        "Отправь мне ссылку на видео из TikTok, Instagram, YouTube Shorts или Pinterest"
    )
