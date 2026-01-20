"""
SaveNow API Downloader для YouTube

Использует RapidAPI wrapper для SaveNow.to — CDN проксирует видео,
наш IP не банится YouTube (в отличие от googlevideo.com URLs).

API: YouTube Info & Download API
Host: youtube-info-download-api.p.rapidapi.com
Backend: SaveNow.to (CDN: *.savenow.to)

Flow:
1. GET /ajax/download.php → получаем job ID + progress_url
2. Poll /ajax/progress.php каждые 3-5 сек
3. Когда success=1 → download_url готов (*.savenow.to CDN)
4. Скачиваем файл
"""
import os
import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import aiohttp
from curl_cffi import requests as curl_requests

from shared.utils.video_fixer import (
    fix_video,
    ensure_faststart,
    download_thumbnail,
    get_video_dimensions,
    get_video_duration
)

logger = logging.getLogger(__name__)

# Константы
RAPIDAPI_HOST = "youtube-info-download-api.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_HOST}"
DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_MB = 2000  # 2GB - лимит Telegram
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 1200  # 20 минут для больших видео
POLL_INTERVAL = 5  # Секунд между проверками progress
MAX_POLL_TIME = 600  # 10 минут максимум на подготовку

_executor = ThreadPoolExecutor(max_workers=3)


@dataclass
class SaveNowResult:
    """Результат скачивания через SaveNow API"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    file_size: int = 0
    title: str = ""
    author: str = ""
    duration: int = 0
    thumbnail_path: Optional[str] = None  # Локальный путь к thumbnail
    download_host: Optional[str] = None  # CDN host для логов
    error: Optional[str] = None


def get_quality_for_duration(duration_seconds: int) -> str:
    """
    Выбор качества видео по длительности

    < 60 мин → 720 (отличное качество, ~100-300MB)
    60-180 мин → 480 (экономия, влезает в 2GB)
    > 180 мин → 360 (очень длинные видео)
    """
    if duration_seconds < 3600:      # < 60 мин
        return "720"
    elif duration_seconds < 10800:   # < 180 мин
        return "480"
    else:
        return "360"


class SaveNowDownloader:
    """
    Загрузчик YouTube через SaveNow API (RapidAPI wrapper)

    Преимущества:
    - CDN проксирует видео (*.savenow.to)
    - Наш IP не банится YouTube
    - Работает для длинных видео (до 4-5 часов)

    Использование:
        downloader = SaveNowDownloader()
        result = await downloader.download(url)
        if result.success:
            # result.file_path содержит путь к файлу
    """

    def __init__(self):
        self.api_key = os.getenv("RAPIDAPI_KEY", "")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        if not self.api_key:
            logger.warning("[SAVENOW] RAPIDAPI_KEY not set!")

    def _get_headers(self) -> dict:
        """Заголовки для RapidAPI"""
        return {
            "X-RapidAPI-Host": RAPIDAPI_HOST,
            "X-RapidAPI-Key": self.api_key
        }

    def _get_youtube_thumbnail(self, url: str) -> Optional[str]:
        """
        Получить URL thumbnail напрямую с YouTube.

        YouTube thumbnail URLs:
        - maxresdefault.jpg (1280x720) - лучшее качество
        - hqdefault.jpg (480x360)
        - mqdefault.jpg (320x180)
        - default.jpg (120x90)
        """
        import re

        # Извлекаем video_id из URL
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        ]

        video_id = None
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                break

        if not video_id:
            logger.warning(f"[SAVENOW] Could not extract video_id from URL: {url}")
            return None

        # Пробуем maxresdefault, fallback на hqdefault
        thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
        logger.info(f"[SAVENOW] Using YouTube thumbnail: {thumbnail_url}")
        return thumbnail_url

    def _log_quota_headers(self, headers: dict):
        """
        Логирует quota headers из ответа RapidAPI для мониторинга остатка пакета.

        RapidAPI отправляет:
        - x-ratelimit-requests-remaining: оставшиеся запросы
        - x-ratelimit-requests-reset: секунды до сброса
        - x-ratelimit-{billing-object}-remaining: для unit-based billing
        """
        # Ищем все headers связанные с quota
        quota_info = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if 'ratelimit' in key_lower or 'rate-limit' in key_lower:
                quota_info[key] = value

        if quota_info:
            # Основные метрики
            remaining = quota_info.get('x-ratelimit-requests-remaining', 'N/A')
            reset_sec = quota_info.get('x-ratelimit-requests-reset', 'N/A')

            # Ищем unit-based limits (для plans типа Pro с units)
            units_remaining = None
            for key, value in quota_info.items():
                if 'remaining' in key.lower() and 'requests' not in key.lower():
                    units_remaining = f"{key}={value}"
                    break

            if units_remaining:
                logger.info(f"[SAVENOW-QUOTA] requests_remaining={remaining}, reset_sec={reset_sec}, {units_remaining}")
            else:
                logger.info(f"[SAVENOW-QUOTA] requests_remaining={remaining}, reset_sec={reset_sec}")

            # Предупреждение если квота близка к лимиту
            try:
                remaining_int = int(remaining)
                if remaining_int < 100:
                    logger.warning(f"[SAVENOW-QUOTA] LOW QUOTA WARNING: only {remaining_int} requests remaining!")
            except (ValueError, TypeError):
                pass

    def _log_unit_cost(self, data: dict):
        """
        Логирует unit_cost из ответа API для подсчёта реальных затрат.

        API может возвращать:
        - unit_cost / units / cost: сколько units списалось
        - price: цена в USD

        ВАЖНО: Нужно проверить реальный response чтобы узнать точные поля!
        """
        # Ищем поля связанные с cost/units
        cost_fields = ['unit_cost', 'units', 'cost', 'price', 'credits', 'units_used']
        for field in cost_fields:
            if field in data:
                logger.info(f"[SAVENOW-COST] {field}={data[field]}")
                return

        # Если не нашли — логируем для отладки
        # (раскомментировать при тестировании)
        # logger.debug(f"[SAVENOW-COST] No cost field found in response keys: {list(data.keys())}")

    async def download(self, url: str, quality: str = "720") -> SaveNowResult:
        """
        Скачать видео с YouTube через SaveNow API

        Args:
            url: URL видео
            quality: Качество (360, 480, 720, 1080). По умолчанию 720.

        Returns:
            SaveNowResult с путём к файлу
        """
        if not self.api_key:
            return SaveNowResult(success=False, error="RAPIDAPI_KEY not configured")

        try:
            logger.info(f"[SAVENOW] Starting download: {url}, quality={quality}")

            # Шаг 1: Запускаем job
            job = await self._start_download_job(url, quality)
            if not job.get("success"):
                return SaveNowResult(
                    success=False,
                    error=job.get("error", "Failed to start download job")
                )

            job_id = job.get("id")
            progress_url = job.get("progress_url")
            title = job.get("title", "video")
            thumbnail_url = job.get("thumbnail")

            logger.info(f"[SAVENOW] Job started: id={job_id}, title='{title[:50]}', thumbnail={'YES' if thumbnail_url else 'NO'}")

            # Шаг 2: Poll progress до готовности
            download_url = await self._poll_progress(job_id, progress_url)
            if not download_url:
                return SaveNowResult(
                    success=False,
                    error="Download preparation timeout or failed"
                )

            # Логируем CDN host
            parsed = urlparse(download_url)
            download_host = parsed.netloc
            logger.info(f"[SAVENOW] Download ready: host={download_host}")

            # Проверяем что это действительно SaveNow CDN
            if "googlevideo.com" in download_host:
                logger.warning(f"[SAVENOW] WARNING: Got googlevideo.com URL, IP may be banned!")

            # Шаг 3: Скачиваем файл
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._download_file,
                    download_url,
                    title,
                    thumbnail_url,
                    download_host
                ),
                timeout=DOWNLOAD_TIMEOUT
            )

            return result

        except asyncio.TimeoutError:
            return SaveNowResult(success=False, error=f"Download timeout ({DOWNLOAD_TIMEOUT}s)")
        except Exception as e:
            logger.exception(f"[SAVENOW] Download error: {e}")
            return SaveNowResult(success=False, error=str(e)[:100])

    async def download_adaptive(self, url: str, duration_hint: int = 0) -> SaveNowResult:
        """
        Скачать с адаптивным качеством по длительности

        Args:
            url: URL видео
            duration_hint: Примерная длительность в секундах (если известна)

        Returns:
            SaveNowResult с путём к файлу
        """
        quality = get_quality_for_duration(duration_hint)
        logger.info(f"[SAVENOW] Adaptive quality: duration={duration_hint}s -> quality={quality}")
        return await self.download(url, quality)

    async def _start_download_job(self, url: str, quality: str) -> dict:
        """
        Запустить job скачивания через API

        Returns:
            dict с полями: success, id, progress_url, title, thumbnail, error
        """
        try:
            # Формат: 360, 480, 720, 1080, 1440, 4k
            # Также поддерживает: mp3, m4a, webm, aac, flac, wav
            endpoint = f"{RAPIDAPI_BASE_URL}/ajax/download.php"

            params = {
                "format": quality,
                "url": url,
                "allow_extended_duration": "1"  # Разрешаем длинные видео
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    endpoint,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"[SAVENOW] API error {resp.status}: {error_text[:200]}")
                        return {"success": False, "error": f"API error: {resp.status}"}

                    data = await resp.json()

                    # DEBUG: При тестировании раскомментировать для просмотра полного response
                    logger.info(f"[SAVENOW] Job response keys: {list(data.keys())}")

                    # Логируем quota headers для мониторинга
                    self._log_quota_headers(dict(resp.headers))

                    # Логируем unit_cost для подсчёта затрат
                    self._log_unit_cost(data)

                    # Проверяем на ошибки
                    if data.get("error"):
                        error_msg = data.get("message", data.get("error", "Unknown error"))
                        return {"success": False, "error": error_msg}

                    # Парсим ответ
                    # Ожидаемые поля: id, progress_url или progress, title, thumbnail
                    job_id = data.get("id") or data.get("job_id") or data.get("download_id")
                    progress_url = data.get("progress_url") or data.get("progress")

                    # Если нет progress_url, строим его сами
                    if not progress_url and job_id:
                        progress_url = f"{RAPIDAPI_BASE_URL}/ajax/progress.php?id={job_id}"

                    # Ищем thumbnail в разных местах response
                    thumbnail = (
                        data.get("thumbnail") or
                        data.get("thumb") or
                        data.get("poster") or
                        (data.get("info") or {}).get("thumbnail") or
                        (data.get("info") or {}).get("thumb") or
                        (data.get("additional_info") or {}).get("thumbnail")
                    )

                    # Если thumbnail не найден — строим URL с YouTube напрямую
                    if not thumbnail:
                        thumbnail = self._get_youtube_thumbnail(url)

                    # Если download_url уже готов (быстрый ответ для коротких видео)
                    if data.get("download_url"):
                        return {
                            "success": True,
                            "id": job_id,
                            "progress_url": progress_url,
                            "download_url": data.get("download_url"),
                            "title": data.get("title", "video"),
                            "thumbnail": thumbnail
                        }

                    if not job_id:
                        logger.error(f"[SAVENOW] No job ID in response: {data}")
                        return {"success": False, "error": "No job ID returned"}

                    return {
                        "success": True,
                        "id": job_id,
                        "progress_url": progress_url,
                        "title": data.get("title", "video"),
                        "thumbnail": thumbnail
                    }

        except asyncio.TimeoutError:
            return {"success": False, "error": "API timeout"}
        except Exception as e:
            logger.exception(f"[SAVENOW] Start job error: {e}")
            return {"success": False, "error": str(e)[:100]}

    async def _poll_progress(self, job_id: str, progress_url: str = None) -> Optional[str]:
        """
        Poll progress endpoint до готовности

        Returns:
            download_url когда готово, None при timeout/error
        """
        if not progress_url:
            progress_url = f"{RAPIDAPI_BASE_URL}/ajax/progress.php?id={job_id}"

        start_time = asyncio.get_event_loop().time()
        last_progress = 0

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time

            if elapsed > MAX_POLL_TIME:
                logger.warning(f"[SAVENOW] Poll timeout after {elapsed:.0f}s")
                return None

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        progress_url,
                        headers=self._get_headers(),
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"[SAVENOW] Progress check failed: {resp.status}")
                            await asyncio.sleep(POLL_INTERVAL)
                            continue

                        data = await resp.json()

                        # Логируем quota (только первый раз чтобы не спамить)
                        if elapsed < POLL_INTERVAL * 2:
                            self._log_quota_headers(dict(resp.headers))

                        # Проверяем статус
                        # Возможные поля: success, status, progress, download_url
                        success = data.get("success")
                        status = data.get("status", "")
                        progress = data.get("progress", 0)
                        download_url = data.get("download_url") or data.get("url")

                        # Логируем прогресс (не спамим если не изменился)
                        if progress != last_progress:
                            logger.info(f"[SAVENOW] Progress: {progress}%, status={status}")
                            last_progress = progress

                        # Готово!
                        if success == 1 or success == True or status == "completed":
                            if download_url:
                                logger.info(f"[SAVENOW] Download ready after {elapsed:.0f}s")
                                return download_url
                            else:
                                logger.warning(f"[SAVENOW] Success but no download_url: {data}")

                        # Ошибка
                        if data.get("error") or status in ("error", "failed"):
                            error_msg = data.get("message", data.get("error", "Unknown error"))
                            logger.error(f"[SAVENOW] Job failed: {error_msg}")
                            return None

            except Exception as e:
                logger.warning(f"[SAVENOW] Poll error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    def _download_file(
        self,
        download_url: str,
        title: str,
        thumbnail_url: Optional[str],
        download_host: str
    ) -> SaveNowResult:
        """Синхронное скачивание файла"""
        try:
            logger.info(f"[SAVENOW] Downloading from CDN: {download_host}")

            # Скачиваем с потоковой передачей
            response = curl_requests.get(
                download_url,
                impersonate='chrome',
                timeout=DOWNLOAD_TIMEOUT,
                allow_redirects=True,
                stream=True
            )
            response.raise_for_status()

            # Генерируем путь
            unique_id = str(uuid.uuid4())[:12]
            file_path = os.path.join(DOWNLOAD_DIR, f"savenow_{unique_id}.mp4")

            # Сохраняем потоково (чанками по 1MB)
            total_size = 0
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)

            logger.info(f"[SAVENOW] Downloaded: {total_size / 1024 / 1024:.1f} MB")

            # Проверяем размер
            if total_size > MAX_FILE_SIZE_BYTES:
                os.remove(file_path)
                size_mb = total_size // 1024 // 1024
                return SaveNowResult(
                    success=False,
                    error=f"Video too large ({size_mb}MB > 2GB limit)"
                )

            # Фиксим видео (SAR/кодек)
            fix_video(file_path)

            # Гарантируем faststart (moov в начале)
            ensure_faststart(file_path)

            # Получаем реальные размеры и duration после фикса
            width, height = get_video_dimensions(file_path)
            duration = get_video_duration(file_path)

            # Скачиваем thumbnail
            thumb_path = None
            if thumbnail_url:
                thumb_path = download_thumbnail(thumbnail_url)
                if thumb_path:
                    logger.info(f"[SAVENOW] Thumbnail ready: {thumb_path}")

            # Финальный размер файла
            file_size = os.path.getsize(file_path)

            # Безопасное имя файла
            safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()[:50]
            filename = f"{safe_title or 'video'}.mp4"

            logger.info(f"[SAVENOW] SUCCESS: {file_size / 1024 / 1024:.1f} MB, "
                       f"{width}x{height}, {duration}s, host={download_host}")

            return SaveNowResult(
                success=True,
                file_path=file_path,
                filename=filename,
                file_size=file_size,
                title=title,
                duration=duration,
                thumbnail_path=thumb_path,
                download_host=download_host
            )

        except Exception as e:
            logger.exception(f"[SAVENOW] File download error: {e}")
            return SaveNowResult(success=False, error=str(e)[:100])

    async def get_video_info(self, url: str) -> dict:
        """
        Получить информацию о видео без скачивания

        Returns:
            dict с полями: success, title, duration, thumbnail, error
        """
        try:
            endpoint = f"{RAPIDAPI_BASE_URL}/ajax/api.php"

            params = {
                "function": "i",
                "u": url
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    endpoint,
                    params=params,
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return {"success": False, "error": f"API error: {resp.status}"}

                    data = await resp.json()

                    if data.get("error"):
                        return {"success": False, "error": data.get("message", "Unknown error")}

                    return {
                        "success": True,
                        "title": data.get("title", "video"),
                        "duration": data.get("duration", 0),
                        "thumbnail": data.get("thumbnail") or data.get("thumb"),
                        "author": data.get("author") or data.get("channel")
                    }

        except Exception as e:
            logger.exception(f"[SAVENOW] Get info error: {e}")
            return {"success": False, "error": str(e)[:100]}

    async def cleanup(self, *paths: str):
        """Удалить файлы"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"[SAVENOW] Cleaned up: {path}")
                except Exception as e:
                    logger.warning(f"[SAVENOW] Cleanup error {path}: {e}")
