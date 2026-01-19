"""
RapidAPI Social Download All In One

API для скачивания видео из:
- Instagram (посты, reels, stories, IGTV)
- TikTok
- YouTube Shorts
- Pinterest
- Twitter/X
- Facebook
- и др.

Документация: https://rapidapi.com/developer-developer/api/social-download-all-in-one
"""
import os
import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import aiohttp
from curl_cffi import requests as curl_requests

from shared.utils.video_fixer import fix_video, ensure_faststart

logger = logging.getLogger(__name__)

# Константы
RAPIDAPI_URL = "https://social-download-all-in-one.p.rapidapi.com/v1/social/autolink"
DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_MB = 2000  # 2GB - лимит Telegram
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 1200  # 20 минут для больших YouTube видео (8-часовое видео = 2-4GB)

_executor = ThreadPoolExecutor(max_workers=3)


@dataclass
class RapidAPIMedia:
    """Медиа из ответа RapidAPI"""
    url: str
    type: str  # "video", "image", "audio"
    quality: str = ""
    extension: str = ""


@dataclass
class RapidAPIResult:
    """Результат RapidAPI запроса"""
    success: bool
    medias: List[RapidAPIMedia] = None
    title: str = ""
    author: str = ""
    duration: int = 0  # Длительность видео в секундах
    error: Optional[str] = None


@dataclass
class DownloadedFile:
    """Скачанный файл"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    file_size: int = 0
    is_photo: bool = False
    title: str = ""
    author: str = ""
    error: Optional[str] = None


@dataclass
class CarouselResult:
    """Результат скачивания карусели"""
    success: bool
    files: List[DownloadedFile] = None
    title: str = ""
    author: str = ""
    has_video: bool = False  # Есть ли видео для извлечения аудио
    error: Optional[str] = None


# === HELPER FUNCTIONS ===

def get_quality_for_duration(duration_seconds: int) -> int:
    """
    Выбор качества видео по длительности для YouTube

    С Local Bot API Server (лимит 2GB):
    < 60 мин → 720p (отличное качество, ~100-300MB)
    ≥ 60 мин → 480p (экономия трафика, влезает в 2GB)
    """
    if duration_seconds < 3600:      # < 60 мин
        return 720
    else:                            # ≥ 60 мин
        return 480


def select_best_media_by_quality(medias: List[RapidAPIMedia], desired_quality: int) -> Optional[RapidAPIMedia]:
    """
    Выбрать видео ближайшее к желаемому качеству

    Логика (предпочитаем ЛУЧШЕЕ качество):
    1. Точное совпадение (480p) → берём его
    2. Нет точного → берём ближайшее СВЕРХУ (720p для 480p)
    3. Нет сверху → берём максимальное снизу (360p если 720p недоступно)

    Пример: доступны 360p, 720p; запрос 480p → вернет 720p
    Пример: доступны 360p, 480p, 720p; запрос 480p → вернет 480p (точное)
    """
    videos = [m for m in medias if m.type == "video"]
    if not videos:
        return None

    # Парсим качество из строки ("720p" или "mp4 (720p) avc1" -> 720)
    def parse_quality(quality_str: str) -> int:
        try:
            import re
            # Ищем паттерн вида "720p", "1080p", etc
            match = re.search(r'(\d+)p', quality_str.lower())
            if match:
                return int(match.group(1))
            return 0
        except (ValueError, AttributeError):
            return 0

    # Создаём список (quality_int, priority, media)
    # priority: 2=avc1/h264 (лучше для Telegram), 1=vp9, 0=av01/другое
    videos_with_quality = []
    for v in videos:
        q = parse_quality(v.quality)
        if q > 0:
            # Определяем приоритет формата
            quality_lower = v.quality.lower()
            if 'avc1' in quality_lower or 'h264' in quality_lower:
                priority = 2  # Лучший формат для Telegram
            elif 'vp9' in quality_lower:
                priority = 1
            else:
                priority = 0
            videos_with_quality.append((q, priority, v))

    if not videos_with_quality:
        return videos[0]

    # Сортируем по качеству, потом по приоритету формата
    videos_with_quality.sort(key=lambda x: (x[0], -x[1]))

    # 1. Точное совпадение (предпочитаем avc1)
    for q, priority, media in videos_with_quality:
        if q == desired_quality:
            return media

    # 2. Ближайшее СВЕРХУ (минимальное среди больших, предпочитаем avc1)
    for q, priority, media in videos_with_quality:
        if q > desired_quality:
            return media  # Возвращаем первое больше (минимальное сверху с лучшим форматом)

    # 3. Нет сверху - берем максимальное снизу
    return videos_with_quality[-1][2]


# === DOWNLOADER CLASS ===

class RapidAPIDownloader:
    """
    Загрузчик через RapidAPI Social Download All In One

    Использование:
        downloader = RapidAPIDownloader()
        result = await downloader.download(url)
        if result.success:
            # result.file_path содержит путь к файлу
    """

    def __init__(self):
        self.api_key = os.getenv("RAPIDAPI_KEY", "")
        self.api_host = os.getenv("RAPIDAPI_HOST", "social-download-all-in-one.p.rapidapi.com")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        if not self.api_key:
            logger.warning("RAPIDAPI_KEY not set!")

    async def get_media_info(self, url: str) -> RapidAPIResult:
        """
        Получить информацию о медиа через RapidAPI

        Returns:
            RapidAPIResult с URLs для скачивания
        """
        if not self.api_key:
            return RapidAPIResult(success=False, error="RAPIDAPI_KEY not configured")

        headers = {
            "Content-Type": "application/json",
            "X-RapidAPI-Host": self.api_host,
            "X-RapidAPI-Key": self.api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    RAPIDAPI_URL,
                    json={"url": url},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"RapidAPI error {resp.status}: {error_text[:200]}")
                        return RapidAPIResult(
                            success=False,
                            error=f"API error: {resp.status}"
                        )

                    data = await resp.json()
                    return self._parse_response(data)

        except asyncio.TimeoutError:
            return RapidAPIResult(success=False, error="API timeout")
        except Exception as e:
            logger.exception(f"RapidAPI request error: {e}")
            return RapidAPIResult(success=False, error=str(e)[:100])

    def _parse_response(self, data: dict) -> RapidAPIResult:
        """Парсит ответ RapidAPI"""
        try:
            # Проверяем на ошибки
            if data.get("error"):
                return RapidAPIResult(
                    success=False,
                    error=data.get("message", "Unknown error")
                )

            medias = []
            raw_medias = data.get("medias", [])

            for m in raw_medias:
                media_url = m.get("url", "")
                if not media_url:
                    continue

                media_type = m.get("type", "video")
                quality = m.get("quality", "")
                extension = m.get("extension", "")

                medias.append(RapidAPIMedia(
                    url=media_url,
                    type=media_type,
                    quality=quality,
                    extension=extension
                ))

            if not medias:
                return RapidAPIResult(
                    success=False,
                    error="No media found"
                )

            # Извлекаем длительность (может быть в секундах или "MM:SS" формате)
            duration = 0
            duration_raw = data.get("duration", 0)
            if isinstance(duration_raw, int):
                duration = duration_raw
            elif isinstance(duration_raw, str) and ":" in duration_raw:
                # Парсим "MM:SS" или "HH:MM:SS"
                try:
                    parts = duration_raw.split(":")
                    if len(parts) == 2:  # MM:SS
                        duration = int(parts[0]) * 60 + int(parts[1])
                    elif len(parts) == 3:  # HH:MM:SS
                        duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except (ValueError, IndexError):
                    pass

            return RapidAPIResult(
                success=True,
                medias=medias,
                title=data.get("title", "")[:100],
                author=data.get("author", "") or data.get("username", ""),
                duration=duration
            )

        except Exception as e:
            logger.exception(f"Parse response error: {e}")
            return RapidAPIResult(success=False, error=str(e)[:100])

    async def download(self, url: str, adaptive_quality: bool = False) -> DownloadedFile:
        """
        Скачать медиа по URL через RapidAPI

        1. Получает прямые ссылки через API
        2. Скачивает с адаптивным качеством (для YouTube) или лучшее
        3. Возвращает путь к файлу

        Args:
            url: URL видео
            adaptive_quality: Если True, выбирает качество по длительности (для YouTube)
        """
        # Получаем инфо о медиа
        info = await self.get_media_info(url)

        if not info.success:
            return DownloadedFile(success=False, error=info.error)

        # Логируем доступные качества
        available_qualities = [m.quality for m in info.medias if m.type == "video"]
        logger.info(f"[RAPIDAPI] Available qualities: {available_qualities}")

        # Выбираем медиа
        if adaptive_quality and info.duration > 0:
            # Адаптивное качество для YouTube
            desired_quality = get_quality_for_duration(info.duration)
            target_media = select_best_media_by_quality(info.medias, desired_quality)
            selected_quality = getattr(target_media, 'quality', 'unknown') if target_media else 'none'
            logger.info(f"[ADAPTIVE] duration={info.duration}s -> desired={desired_quality}p, selected={selected_quality}")
        else:
            # Обычный режим - берём лучшее видео или фото
            video_media = None
            photo_media = None

            for m in info.medias:
                if m.type == "video" and not video_media:
                    video_media = m
                elif m.type == "image" and not photo_media:
                    photo_media = m

            target_media = video_media or photo_media

        if not target_media:
            return DownloadedFile(success=False, error="No suitable media found")

        is_photo = target_media.type == "image"

        # Скачиваем файл
        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._download_file,
                    target_media.url,
                    is_photo,
                    info.title,
                    info.author
                ),
                timeout=DOWNLOAD_TIMEOUT
            )
            return result

        except asyncio.TimeoutError:
            return DownloadedFile(success=False, error=f"Download timeout ({DOWNLOAD_TIMEOUT}s)")
        except Exception as e:
            logger.exception(f"Download error: {e}")
            return DownloadedFile(success=False, error=str(e)[:100])

    async def download_all(self, url: str) -> CarouselResult:
        """
        Скачать ВСЕ медиа из карусели Instagram

        Возвращает список файлов для отправки как MediaGroup
        """
        info = await self.get_media_info(url)

        if not info.success:
            return CarouselResult(success=False, error=info.error)

        # Собираем уникальные медиа (убираем дубли по URL)
        seen_urls = set()
        unique_medias = []

        for m in info.medias:
            # Пропускаем аудио и дубликаты
            if m.type == "audio" or m.url in seen_urls:
                continue
            seen_urls.add(m.url)
            unique_medias.append(m)

        if not unique_medias:
            return CarouselResult(success=False, error="No media found")

        # Если только 1 медиа - используем обычный download
        if len(unique_medias) == 1:
            result = await self.download(url)
            if result.success:
                return CarouselResult(
                    success=True,
                    files=[result],
                    title=info.title,
                    author=info.author,
                    has_video=not result.is_photo
                )
            return CarouselResult(success=False, error=result.error)

        # Скачиваем все файлы параллельно
        logger.info(f"Downloading carousel: {len(unique_medias)} items")

        loop = asyncio.get_running_loop()
        tasks = []

        for i, media in enumerate(unique_medias[:10]):  # Максимум 10 файлов
            is_photo = media.type == "image"
            tasks.append(
                loop.run_in_executor(
                    _executor,
                    self._download_file,
                    media.url,
                    is_photo,
                    info.title,
                    info.author
                )
            )

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=DOWNLOAD_TIMEOUT * 2
            )
        except asyncio.TimeoutError:
            return CarouselResult(success=False, error="Carousel download timeout")

        # Фильтруем успешные
        files = []
        has_video = False

        for r in results:
            if isinstance(r, DownloadedFile) and r.success:
                files.append(r)
                if not r.is_photo:
                    has_video = True

        if not files:
            return CarouselResult(success=False, error="Failed to download carousel items")

        logger.info(f"Carousel downloaded: {len(files)} files")

        return CarouselResult(
            success=True,
            files=files,
            title=info.title,
            author=info.author,
            has_video=has_video
        )

    def _download_file(
        self,
        media_url: str,
        is_photo: bool,
        title: str,
        author: str
    ) -> DownloadedFile:
        """Синхронное скачивание файла"""
        try:
            # Скачиваем с потоковой передачей (для больших файлов)
            response = curl_requests.get(
                media_url,
                impersonate='chrome',
                timeout=DOWNLOAD_TIMEOUT,
                allow_redirects=True,
                stream=True  # Включаем потоковую передачу
            )
            response.raise_for_status()

            # Определяем расширение
            content_type = response.headers.get('content-type', '')

            if is_photo:
                if 'png' in content_type or media_url.endswith('.png'):
                    ext = 'png'
                elif 'webp' in content_type or media_url.endswith('.webp'):
                    ext = 'webp'
                else:
                    ext = 'jpg'
            else:
                ext = 'mp4'

            # Генерируем путь
            unique_id = str(uuid.uuid4())[:12]
            file_path = os.path.join(DOWNLOAD_DIR, f"{unique_id}.{ext}")

            # Сохраняем потоково (чанками по 1MB)
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB чанки
                    if chunk:
                        f.write(chunk)

            # Фиксим видео (SAR/кодек) для корректного отображения в Telegram
            if not is_photo:
                fix_video(file_path)
                # КРИТИЧНО: Гарантируем faststart (moov в начале) для корректного duration в Telegram
                # fix_video может SKIP если SAR уже OK и кодек H.264, но moov может быть в конце!
                ensure_faststart(file_path)

            file_size = os.path.getsize(file_path)

            # Проверяем размер
            if file_size > MAX_FILE_SIZE_BYTES:
                os.remove(file_path)
                file_size_mb = file_size // 1024 // 1024
                return DownloadedFile(
                    success=False,
                    error=f"Видео слишком большое ({file_size_mb}MB), не могу отправить в Telegram (лимит 2GB)"
                )

            # Формируем имя файла
            safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()[:50]
            filename = f"{safe_title or 'media'}.{ext}"

            return DownloadedFile(
                success=True,
                file_path=file_path,
                filename=filename,
                file_size=file_size,
                is_photo=is_photo,
                title=title,
                author=author
            )

        except Exception as e:
            logger.exception(f"File download error: {e}")
            return DownloadedFile(success=False, error=str(e)[:100])

    async def download_audio(self, url: str) -> DownloadedFile:
        """
        Скачать аудио (если доступно в API)

        Если API не возвращает аудио отдельно, вернёт ошибку.
        В таком случае используйте extract_audio из видео.
        """
        info = await self.get_media_info(url)

        if not info.success:
            return DownloadedFile(success=False, error=info.error)

        # Ищем аудио
        audio_media = None
        for m in info.medias:
            if m.type == "audio":
                audio_media = m
                break

        if not audio_media:
            return DownloadedFile(success=False, error="No audio available")

        # Скачиваем
        try:
            loop = asyncio.get_running_loop()

            def _download():
                response = curl_requests.get(
                    audio_media.url,
                    impersonate='chrome',
                    timeout=DOWNLOAD_TIMEOUT
                )
                response.raise_for_status()

                unique_id = str(uuid.uuid4())[:12]
                ext = audio_media.extension or 'mp3'
                file_path = os.path.join(DOWNLOAD_DIR, f"{unique_id}.{ext}")

                with open(file_path, 'wb') as f:
                    f.write(response.content)

                return DownloadedFile(
                    success=True,
                    file_path=file_path,
                    filename=f"audio.{ext}",
                    file_size=os.path.getsize(file_path),
                    title=info.title,
                    author=info.author
                )

            return await asyncio.wait_for(
                loop.run_in_executor(_executor, _download),
                timeout=DOWNLOAD_TIMEOUT
            )

        except asyncio.TimeoutError:
            return DownloadedFile(success=False, error="Download timeout")
        except Exception as e:
            return DownloadedFile(success=False, error=str(e)[:100])

    async def cleanup(self, *paths: str):
        """Удалить файлы"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Cleanup error {path}: {e}")
