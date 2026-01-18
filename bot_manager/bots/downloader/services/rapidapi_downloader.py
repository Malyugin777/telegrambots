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


@dataclass
class CarouselResult:
    """Результат скачивания карусели"""
    success: bool
    files: List[DownloadedFile] = None
    title: str = ""
    author: str = ""
    has_video: bool = False  # Есть ли видео для извлечения аудио
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

            # Фиксим видео (SAR/кодек) для корректного отображения в Telegram
            if not is_photo:
                self._fix_video(file_path)

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

    def _fix_video(self, video_path: str) -> None:
        """
        Исправляет видео — ЯВНО пересчитывает пиксели для правильного отображения.

        Instagram/TikTok часто отдают видео с неправильными метаданными SAR/DAR.
        iOS Telegram игнорирует SAR и рендерит пиксели напрямую — поэтому нужно
        РЕАЛЬНО масштабировать видео, а не только менять метаданные.

        Логика:
        - SAR = 1:1 и H.264 → ничего не делаем
        - SAR ≠ 1:1 → вычисляем новые размеры и масштабируем пиксели
        """
        import subprocess

        try:
            # Получаем width, height, codec, SAR используя JSON для надёжного парсинга
            probe_cmd = [
                'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,codec_name,sample_aspect_ratio',
                '-of', 'json', video_path
            ]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            probe_output = result.stdout.strip()

            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ
            logger.info(f"[FIX_VIDEO] Probe output: {probe_output[:200]}")

            # Парсим JSON
            import json
            try:
                data = json.loads(probe_output)
                streams = data.get('streams', [])
                if not streams:
                    logger.warning(f"[FIX_VIDEO] No streams in probe output")
                    return
                stream = streams[0]
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                codec = stream.get('codec_name', '')
                sar = stream.get('sample_aspect_ratio', '1:1') or '1:1'
            except json.JSONDecodeError as e:
                logger.warning(f"[FIX_VIDEO] Cannot parse JSON: {e}")
                return

            logger.info(f"[FIX_VIDEO] Parsed: {width}x{height}, codec={codec}, SAR={sar}")

            if not width or not height:
                logger.warning(f"[FIX_VIDEO] Invalid video dimensions: {width}x{height}")
                return

            # Нормализуем SAR (1/1 -> 1:1)
            sar_normalized = sar.replace('/', ':')

            # SAR считается правильным если 1:1, N/A или пустой
            sar_is_ok = sar_normalized in ('1:1', 'N/A', '')

            # Если уже H.264 с правильным SAR - ничего не делаем
            if codec == 'h264' and sar_is_ok:
                logger.info(f"[FIX_VIDEO] SKIP - already OK: {width}x{height}, codec={codec}, sar={sar}")
                return

            output_path = video_path.rsplit('.', 1)[0] + "_fixed.mp4"

            if sar_is_ok:
                # SAR правильный, но кодек не H.264 — перекодируем в H.264
                logger.info(f"[FIX_VIDEO] RECODE: {width}x{height}, codec {codec} -> h264")
                fix_cmd = [
                    'ffmpeg', '-i', video_path,
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '20',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-y', output_path
                ]
            else:
                # SAR неправильный — ЯВНО вычисляем новые размеры
                try:
                    # Парсим SAR (например "9:10" или "9/10")
                    sar_clean = sar_normalized.replace('/', ':')
                    sar_parts = sar_clean.split(':')
                    sar_num = int(sar_parts[0])
                    sar_den = int(sar_parts[1]) if len(sar_parts) > 1 else 1

                    # Вычисляем новую ширину с учётом SAR
                    new_width = int(width * sar_num / sar_den)
                    new_height = height

                    # Делаем размеры чётными (требование H.264)
                    new_width = new_width + (new_width % 2)
                    new_height = new_height + (new_height % 2)

                except (ValueError, ZeroDivisionError):
                    # Не удалось распарсить SAR — используем оригинальные размеры
                    new_width = width + (width % 2)
                    new_height = height + (height % 2)

                logger.info(f"[FIX_VIDEO] SCALE: {width}x{height} SAR={sar} -> {new_width}x{new_height} SAR=1:1")

                fix_cmd = [
                    'ffmpeg', '-i', video_path,
                    '-vf', f'scale={new_width}:{new_height},setsar=1:1',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '20',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-movflags', '+faststart',
                    '-y', output_path
                ]

            result = subprocess.run(fix_cmd, capture_output=True, timeout=180)

            if result.returncode == 0 and os.path.exists(output_path):
                # Заменяем оригинал
                os.remove(video_path)
                os.rename(output_path, video_path)
                logger.info(f"[FIX_VIDEO] SUCCESS: {os.path.getsize(video_path)} bytes")
            else:
                # Не удалось — оставляем оригинал
                if os.path.exists(output_path):
                    os.remove(output_path)
                stderr = result.stderr.decode() if result.stderr else 'unknown'
                logger.warning(f"[FIX_VIDEO] FAILED: {stderr[:200]}")

        except Exception as e:
            logger.warning(f"[FIX_VIDEO] ERROR: {e}")

    async def cleanup(self, *paths: str):
        """Удалить файлы"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.warning(f"Cleanup error {path}: {e}")
