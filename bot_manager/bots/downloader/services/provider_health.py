"""
Provider Health Check Service

Быстрая проверка доступности провайдеров (как в платёжках).
5 секунд на пинг → OK/FAIL → fallback

Каждый провайдер имеет свой метод проверки:
- ytdlp: extract_info без скачивания
- pytubefix: создание YouTube объекта + check_availability
- rapidapi: HEAD запрос к API
- savenow: POST запрос на создание задачи
"""
import asyncio
import logging
import os
from typing import Tuple
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3)

# RapidAPI config
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "social-download-all-in-one.p.rapidapi.com")


async def check_provider(name: str, url: str, timeout: int = 5) -> Tuple[bool, str]:
    """
    Быстрая проверка доступности провайдера.

    Args:
        name: Имя провайдера (ytdlp, pytubefix, rapidapi, savenow)
        url: URL для скачивания
        timeout: Максимальное время проверки в секундах

    Returns:
        (is_available, error_reason)
        - (True, "") если провайдер доступен
        - (False, "причина") если недоступен
    """
    try:
        if name == "ytdlp":
            return await _ping_ytdlp(url, timeout)
        elif name == "pytubefix":
            return await _ping_pytubefix(url, timeout)
        elif name == "rapidapi":
            return await _ping_rapidapi(url, timeout)
        elif name == "savenow":
            return await _ping_savenow(url, timeout)
        else:
            logger.warning(f"[PING] Unknown provider: {name}")
            return True, ""  # Пропускаем пинг для неизвестных
    except asyncio.TimeoutError:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)


async def _ping_ytdlp(url: str, timeout: int) -> Tuple[bool, str]:
    """
    Проверка yt-dlp: extract_info без скачивания.
    Быстрая проверка что URL парсится и видео доступно.
    """
    import yt_dlp

    def _extract_sync():
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Не извлекать вложенные плейлисты
            'socket_timeout': timeout,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                raise Exception("No info extracted")
            return info.get('title', 'OK')

    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, _extract_sync),
            timeout=timeout
        )
        logger.info(f"[PING] ytdlp OK: {result[:50]}")
        return True, ""
    except asyncio.TimeoutError:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        error = str(e)
        # Сокращаем длинные ошибки
        if len(error) > 100:
            error = error[:100] + "..."
        return False, error


async def _ping_pytubefix(url: str, timeout: int) -> Tuple[bool, str]:
    """
    Проверка pytubefix: создание YouTube объекта.
    Проверяет что видео существует и доступно.
    """
    from pytubefix import YouTube

    def _check_sync():
        yt = YouTube(url)
        # Пробуем получить заголовок (это триггерит запрос к YouTube)
        title = yt.title
        # Проверяем что есть стримы
        streams = yt.streams.filter(adaptive=True, file_extension='mp4')
        if not streams:
            raise Exception("No streams available")
        return title

    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(_executor, _check_sync),
            timeout=timeout
        )
        logger.info(f"[PING] pytubefix OK: {result[:50]}")
        return True, ""
    except asyncio.TimeoutError:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        error = str(e)
        if len(error) > 100:
            error = error[:100] + "..."
        return False, error


async def _ping_rapidapi(url: str, timeout: int) -> Tuple[bool, str]:
    """
    Проверка RapidAPI: POST запрос на получение информации.
    Проверяет что API отвечает и URL валиден.
    """
    import aiohttp

    if not RAPIDAPI_KEY:
        return False, "RAPIDAPI_KEY not configured"

    api_url = f"https://{RAPIDAPI_HOST}/v1/social/autolink"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json={"url": url},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("error"):
                        return False, data.get("error", "Unknown error")
                    logger.info(f"[PING] rapidapi OK")
                    return True, ""
                elif resp.status == 429:
                    return False, "Rate limit exceeded (429)"
                elif resp.status == 403:
                    return False, "API key invalid or expired (403)"
                else:
                    return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)


async def _ping_savenow(url: str, timeout: int) -> Tuple[bool, str]:
    """
    Проверка SaveNow: POST запрос на создание задачи.
    SaveNow работает асинхронно, поэтому проверяем только что API принимает URL.
    """
    import aiohttp

    api_url = "https://api.savenow.co/v1/download"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                api_url,
                json={"url": url},
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("error"):
                        return False, data.get("error", "Unknown error")
                    logger.info(f"[PING] savenow OK")
                    return True, ""
                elif resp.status == 429:
                    return False, "Rate limit (429)"
                else:
                    return False, f"HTTP {resp.status}"
    except asyncio.TimeoutError:
        return False, f"Timeout ({timeout}s)"
    except Exception as e:
        return False, str(e)
