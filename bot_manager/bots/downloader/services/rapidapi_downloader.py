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

logger = logging.getLogger(__name__)

# Константы
RAPIDAPI_URL = "https://social-download-all-in-one.p.rapidapi.com/v1/social/autolink"
DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 60

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

            return RapidAPIResult(
                success=True,
                medias=medias,
                title=data.get("title", "")[:100],
                author=data.get("author", "") or data.get("username", "")
            )

        except Exception as e:
            logger.exception(f"Parse response error: {e}")
            return RapidAPIResult(success=False, error=str(e)[:100])

    async def download(self, url: str) -> DownloadedFile:
        """
        Скачать медиа по URL через RapidAPI

        1. Получает прямые ссылки через API
        2. Скачивает лучшее качество
        3. Возвращает путь к файлу
        """
        # Получаем инфо о медиа
        info = await self.get_media_info(url)

        if not info.success:
            return DownloadedFile(success=False, error=info.error)

        # Выбираем лучшее видео или фото
        video_media = None
        photo_media = None

        for m in info.medias:
            if m.type == "video" and not video_media:
                video_media = m
            elif m.type == "image" and not photo_media:
                photo_media = m

        # Приоритет: видео > фото
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

    def _download_file(
        self,
        media_url: str,
        is_photo: bool,
        title: str,
        author: str
    ) -> DownloadedFile:
        """Синхронное скачивание файла"""
        try:
            # Скачиваем
            response = curl_requests.get(
                media_url,
                impersonate='chrome',
                timeout=DOWNLOAD_TIMEOUT,
                allow_redirects=True
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

            # Сохраняем
            with open(file_path, 'wb') as f:
                f.write(response.content)

            file_size = os.path.getsize(file_path)

            # Проверяем размер
            if file_size > MAX_FILE_SIZE_BYTES:
                os.remove(file_path)
                return DownloadedFile(
                    success=False,
                    error=f"File too large ({file_size // 1024 // 1024}MB > {MAX_FILE_SIZE_MB}MB)"
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
