"""
Сервис скачивания видео через yt-dlp

Поддерживаемые платформы:
- TikTok (vm.tiktok.com, tiktok.com) — без водяного знака
- Instagram (фото, видео, карусели, истории)
- YouTube Shorts (youtube.com/shorts/)
- Pinterest (фото и видео)
"""
import os
import re
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
from curl_cffi import requests as curl_requests

# Import rate limiting для ffmpeg
try:
    from ..services.cache import acquire_ffmpeg_slot, release_ffmpeg_slot
    RATE_LIMITING_ENABLED = True
except ImportError:
    RATE_LIMITING_ENABLED = False
    logger.warning("Rate limiting не загружен - ffmpeg будет запускаться без ограничений")

logger = logging.getLogger(__name__)

# Chrome impersonate target для TikTok
CHROME_TARGET = ImpersonateTarget.from_str('chrome')

# Константы
DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_YOUTUBE_DOCUMENT_MB = 2048  # 2GB для YouTube полных видео
MAX_YOUTUBE_DOCUMENT_BYTES = MAX_YOUTUBE_DOCUMENT_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 120  # секунд (для обычных видео: Instagram, TikTok, Pinterest, YouTube Shorts)
YOUTUBE_DOWNLOAD_TIMEOUT = 1200  # секунд (20 минут для полных YouTube видео до 2GB)
AUDIO_BITRATE = "320"  # kbps

# Пул потоков для синхронных операций yt-dlp
_executor = ThreadPoolExecutor(max_workers=5)


@dataclass
class MediaInfo:
    """Информация о медиафайле"""
    title: str = "video"
    author: str = "unknown"
    duration: int = 0
    thumbnail: Optional[str] = None
    platform: str = "unknown"


@dataclass
class DownloadResult:
    """Результат скачивания"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    info: MediaInfo = field(default_factory=MediaInfo)
    file_size: int = 0
    error: Optional[str] = None
    is_photo: bool = False  # Для фото из Instagram/Pinterest
    send_as_document: bool = False  # Для больших YouTube видео (50MB-2GB)


class VideoDownloader:
    """
    Асинхронный загрузчик видео через yt-dlp

    Пример использования:
        downloader = VideoDownloader()
        result = await downloader.download(url)
        if result.success:
            await bot.send_video(chat_id, result.file_path)
            await downloader.cleanup(result.file_path)
    """

    def __init__(self):
        """Инициализация загрузчика"""
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    def _get_video_options(self, output_path: str, url: str = "", progress_hook=None) -> dict:
        """Опции yt-dlp для скачивания видео (оптимизировано для скорости)"""

        # Для TikTok предпочитаем H.264 (лучше совместимость с Telegram)
        is_tiktok = 'tiktok' in url.lower()
        # Для YouTube полных видео ограничиваем качество 720p для меньшего размера
        is_youtube_full = ('youtube.com' in url.lower() or 'youtu.be' in url.lower()) and '/shorts/' not in url.lower()
        # Для Pinterest пробуем все форматы (HLS, mp4, любые)
        is_pinterest = 'pinterest' in url.lower() or 'pin.it' in url.lower()

        if is_tiktok:
            # H.264 форматы для TikTok (без проблем с SAR)
            format_string = 'best[ext=mp4][vcodec^=avc]/best[ext=mp4][vcodec^=h264]/best[ext=mp4]/best'
        elif is_youtube_full:
            # YouTube полные видео - макс 720p для уменьшения размера
            format_string = 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best'
        elif is_pinterest:
            # Pinterest видео - пробуем все возможные форматы (HLS, mp4, webm)
            format_string = 'best[ext=mp4]/best[ext=webm]/bestvideo+bestaudio/best'
        else:
            format_string = 'best[ext=mp4]/best'

        # Выбираем socket_timeout в зависимости от платформы
        socket_timeout = 60 if is_youtube_full else 30

        opts = {
            # Основные настройки
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,

            # Имитация браузера (критично для TikTok)
            'impersonate': CHROME_TARGET,

            # Формат: быстрое скачивание - берём готовый mp4, не merge
            'format': format_string,
            'merge_output_format': 'mp4',

            # Путь сохранения
            'outtmpl': output_path,

            # Сеть - оптимизация скорости
            'socket_timeout': socket_timeout,  # 60 для YouTube Full, 30 для остальных
            'retries': 2,
            'fragment_retries': 2,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'concurrent_fragment_downloads': 5,  # Параллельное скачивание
            'buffersize': 1024 * 64,  # 64KB буфер

            # YouTube: ios клиент быстрее отдаёт готовые mp4
            'extractor_args': {
                'youtube': {'player_client': ['ios', 'android']},
            },
        }

        # Добавляем progress_hooks если передан
        if progress_hook:
            opts['progress_hooks'] = [progress_hook]

        return opts

    def _get_audio_options(self, output_path: str) -> dict:
        """Опции yt-dlp для извлечения аудио (MP3 320kbps)"""
        return {
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,

            # Имитация браузера (критично для TikTok)
            'impersonate': CHROME_TARGET,

            'format': 'bestaudio/best',
            'outtmpl': output_path,

            # Конвертация в MP3 320kbps
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': AUDIO_BITRATE,
            }],

            'socket_timeout': 30,
            'retries': 5,
            'nocheckcertificate': True,
            'geo_bypass': True,

            'extractor_args': {
                'youtube': {'player_client': ['android', 'web']},
            },
        }

    def _generate_filepath(self, ext: str = "mp4") -> str:
        """Генерирует уникальный путь к файлу"""
        unique_id = str(uuid.uuid4())[:12]
        return os.path.join(DOWNLOAD_DIR, f"{unique_id}.{ext}")

    def _extract_info(self, info: dict) -> MediaInfo:
        """Извлекает информацию из ответа yt-dlp"""
        return MediaInfo(
            title=info.get('title', 'video')[:100],
            author=info.get('uploader') or info.get('channel') or info.get('creator') or 'unknown',
            duration=int(info.get('duration', 0)),
            thumbnail=info.get('thumbnail'),
            platform=info.get('extractor', 'unknown'),
        )

    def _sanitize_filename(self, title: str, ext: str) -> str:
        """Очищает название для использования как имя файла"""
        safe = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        safe = safe[:50] if safe else "video"
        return f"{safe}.{ext}"

    async def download(self, url: str, progress_callback=None) -> DownloadResult:
        """
        Скачивает видео/фото по URL

        Args:
            url: URL для скачивания
            progress_callback: Опциональный callback для прогресса (dict -> None)

        Returns:
            DownloadResult с путём к файлу или ошибкой
        """
        output_path = self._generate_filepath("mp4")

        # Создаём progress_hook для yt-dlp
        progress_hook = None
        if progress_callback:
            def progress_hook(d):
                try:
                    progress_callback(d)
                except Exception:
                    pass  # Игнорируем ошибки callback

        opts = self._get_video_options(output_path, url, progress_hook)

        try:
            loop = asyncio.get_running_loop()

            # Выбираем таймаут в зависимости от платформы
            is_youtube_full = ('youtube.com' in url.lower() or 'youtu.be' in url.lower()) and '/shorts/' not in url.lower()
            timeout = YOUTUBE_DOWNLOAD_TIMEOUT if is_youtube_full else DOWNLOAD_TIMEOUT

            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._download_sync, url, opts, False),
                timeout=timeout
            )

            # Если ошибка "No video formats" для Pinterest - пробуем как фото
            if not result.success and result.error:
                is_pinterest = 'pinterest' in url or 'pin.it' in url
                is_no_video = 'no video' in result.error.lower() or 'video formats' in result.error.lower()

                if is_pinterest and is_no_video:
                    logger.info(f"Pinterest video not found, trying photo: {url}")
                    return await self.download_photo(url)

            if not result.success:
                return result

            # Исправляем SAR для ВСЕХ видео (не только TikTok!)
            # Pinterest, TikTok, YouTube - у всех может быть неправильный SAR/DAR
            if result.file_path and not result.is_photo:
                # Rate limiting для ffmpeg процессов
                if RATE_LIMITING_ENABLED:
                    # Ожидаем освобождения слота (вместо отказа)
                    while not await acquire_ffmpeg_slot():
                        await asyncio.sleep(0.5)  # Ждём 500ms и пробуем снова

                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(_executor, self._fix_video, result.file_path)
                    # Обновляем размер после исправления
                    if os.path.exists(result.file_path):
                        result.file_size = os.path.getsize(result.file_path)
                finally:
                    if RATE_LIMITING_ENABLED:
                        await release_ffmpeg_slot()

            # Проверяем размер файла
            is_youtube = 'youtube.com' in url.lower() or 'youtu.be' in url.lower()

            if is_youtube:
                # Для YouTube разрешаем до 2GB
                if result.file_size > MAX_YOUTUBE_DOCUMENT_BYTES:
                    await self.cleanup(result.file_path)
                    return DownloadResult(
                        success=False,
                        error=f"Видео слишком большое ({result.file_size // 1024 // 1024}MB > {MAX_YOUTUBE_DOCUMENT_MB}MB). Telegram ограничивает загрузку файлов до 2GB."
                    )
                # Если > 50MB - отправляем как документ
                if result.file_size > MAX_FILE_SIZE_BYTES:
                    result.send_as_document = True
            else:
                # Для остальных платформ - макс 50MB
                if result.file_size > MAX_FILE_SIZE_BYTES:
                    await self.cleanup(result.file_path)
                    return DownloadResult(
                        success=False,
                        error=f"Файл слишком большой ({result.file_size // 1024 // 1024}MB > {MAX_FILE_SIZE_MB}MB)"
                    )

            return result

        except asyncio.TimeoutError:
            logger.error(f"[DOWNLOAD_TIMEOUT] URL={url[:100]}, timeout={timeout}s")
            await self.cleanup(output_path)
            return DownloadResult(
                success=False,
                error=f"Таймаут загрузки ({timeout} сек)"
            )
        except Exception as e:
            logger.exception(f"[DOWNLOAD_EXCEPTION] URL={url[:100]}: {e}")
            await self.cleanup(output_path)
            return DownloadResult(
                success=False,
                error=self._format_error(str(e))
            )

    async def download_audio(self, url: str) -> DownloadResult:
        """
        Скачивает и извлекает аудио из видео (MP3 320kbps)

        Returns:
            DownloadResult с путём к MP3 файлу
        """
        base_path = self._generate_filepath("temp")
        output_template = base_path.rsplit('.', 1)[0]
        opts = self._get_audio_options(output_template)

        try:
            loop = asyncio.get_running_loop()

            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._download_sync, url, opts, True),
                timeout=DOWNLOAD_TIMEOUT
            )

            if not result.success:
                return result

            if result.file_size > MAX_FILE_SIZE_BYTES:
                await self.cleanup(result.file_path)
                return DownloadResult(
                    success=False,
                    error=f"Файл слишком большой ({result.file_size // 1024 // 1024}MB)"
                )

            return result

        except asyncio.TimeoutError:
            await self.cleanup(f"{output_template}.mp3")
            return DownloadResult(
                success=False,
                error=f"Таймаут загрузки ({DOWNLOAD_TIMEOUT} сек)"
            )
        except Exception as e:
            logger.exception(f"Audio download error for {url}: {e}")
            return DownloadResult(
                success=False,
                error=self._format_error(str(e))
            )

    def _download_sync(self, url: str, opts: dict, is_audio: bool = False) -> DownloadResult:
        """Синхронная загрузка (выполняется в thread pool)"""
        import time
        start_time = time.time()

        try:
            logger.info(f"[DOWNLOAD_START] URL={url[:100]}, is_audio={is_audio}")

            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"[DOWNLOAD] Extracting info...")
                info = ydl.extract_info(url, download=True)

                elapsed = time.time() - start_time
                logger.info(f"[DOWNLOAD] Download completed in {elapsed:.1f}s")

                if not info:
                    logger.warning(f"[DOWNLOAD] No info returned from yt-dlp")
                    return DownloadResult(
                        success=False,
                        error="Не удалось получить информацию о видео"
                    )

                file_path = self._find_downloaded_file(info, opts, is_audio)

                if not file_path or not os.path.exists(file_path):
                    logger.error(f"[DOWNLOAD] File not found after download")
                    return DownloadResult(
                        success=False,
                        error="Файл не найден после скачивания"
                    )

                media_info = self._extract_info(info)
                file_size = os.path.getsize(file_path)
                ext = "mp3" if is_audio else "mp4"
                filename = self._sanitize_filename(media_info.title, ext)

                logger.info(f"[DOWNLOAD_SUCCESS] file={file_path}, size={file_size}, time={elapsed:.1f}s")

                return DownloadResult(
                    success=True,
                    file_path=file_path,
                    filename=filename,
                    info=media_info,
                    file_size=file_size
                )

        except yt_dlp.utils.DownloadError as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            logger.error(f"[DOWNLOAD_ERROR] DownloadError after {elapsed:.1f}s: {error_msg[:200]}")
            return DownloadResult(
                success=False,
                error=self._format_error(error_msg)
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.exception(f"[DOWNLOAD_ERROR] Exception after {elapsed:.1f}s: {e}")
            return DownloadResult(
                success=False,
                error=self._format_error(str(e))
            )

    def _find_downloaded_file(self, info: dict, opts: dict, is_audio: bool) -> Optional[str]:
        """Находит скачанный файл"""
        # Способ 1: из requested_downloads
        if 'requested_downloads' in info and info['requested_downloads']:
            filepath = info['requested_downloads'][0].get('filepath')
            if filepath and os.path.exists(filepath):
                return filepath

        # Способ 2: по шаблону
        template = opts.get('outtmpl', '')
        if template:
            base = template.replace('.%(ext)s', '').replace('%(ext)s', '')
            extensions = ['mp3'] if is_audio else ['mp4', 'webm', 'mkv']
            for ext in extensions:
                path = f"{base}.{ext}"
                if os.path.exists(path):
                    return path

        return None

    async def extract_audio(self, video_path: str) -> DownloadResult:
        """
        Извлекает аудио из уже скачанного видео (быстро через ffmpeg)

        Args:
            video_path: Путь к видеофайлу

        Returns:
            DownloadResult с путём к MP3 файлу
        """
        import subprocess

        if not os.path.exists(video_path):
            return DownloadResult(
                success=False,
                error="Видеофайл не найден"
            )

        output_path = video_path.rsplit('.', 1)[0] + ".mp3"

        try:
            loop = asyncio.get_running_loop()

            def _extract():
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-vn',  # Без видео
                    '-acodec', 'libmp3lame',
                    '-ab', f'{AUDIO_BITRATE}k',
                    '-ar', '44100',
                    '-y',  # Перезаписать
                    output_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=180)
                return result.returncode == 0

            success = await asyncio.wait_for(
                loop.run_in_executor(_executor, _extract),
                timeout=180
            )

            if success and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                return DownloadResult(
                    success=True,
                    file_path=output_path,
                    filename="audio.mp3",
                    file_size=file_size
                )
            else:
                return DownloadResult(
                    success=False,
                    error="Ошибка извлечения аудио"
                )

        except asyncio.TimeoutError:
            return DownloadResult(
                success=False,
                error="Таймаут извлечения аудио"
            )
        except Exception as e:
            logger.exception(f"Audio extraction error: {e}")
            return DownloadResult(
                success=False,
                error=str(e)[:100]
            )

    def _fix_video(self, video_path: str) -> Optional[str]:
        """
        Исправляет SAR/DAR для ВСЕХ видео (TikTok, Pinterest, YouTube, Instagram).
        ЯВНО пересчитывает пиксели для правильного отображения.

        Многие платформы отдают HEVC/H264 с неправильными метаданными SAR/DAR.
        iOS Telegram игнорирует SAR и рендерит пиксели напрямую — поэтому нужно
        РЕАЛЬНО масштабировать видео, а не только менять метаданные.

        Логика:
        - SAR = 1:1 и H.264 → ничего не делаем
        - SAR ≠ 1:1 → вычисляем новые размеры и масштабируем пиксели

        Returns:
            Путь к исправленному файлу или None если исправление не требовалось
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
                    return None
                stream = streams[0]
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                codec = stream.get('codec_name', '')
                sar = stream.get('sample_aspect_ratio', '1:1') or '1:1'
            except json.JSONDecodeError as e:
                logger.warning(f"[FIX_VIDEO] Cannot parse JSON: {e}")
                return None

            logger.info(f"[FIX_VIDEO] Parsed: {width}x{height}, codec={codec}, SAR={sar}")

            if not width or not height:
                logger.warning(f"[FIX_VIDEO] Invalid video dimensions: {width}x{height}")
                return None

            # Нормализуем SAR (1/1 -> 1:1)
            sar_normalized = sar.replace('/', ':')

            # SAR считается правильным если 1:1, N/A или пустой
            sar_is_ok = sar_normalized in ('1:1', 'N/A', '')

            # Если уже H.264 с правильным SAR - ничего не делаем
            if codec == 'h264' and sar_is_ok:
                logger.info(f"[FIX_VIDEO] SKIP - already OK: {width}x{height}, codec={codec}, sar={sar}")
                return None

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
                # Удаляем оригинал, переименовываем fixed
                os.remove(video_path)
                os.rename(output_path, video_path)
                new_size = os.path.getsize(video_path)
                logger.info(f"[FIX_VIDEO] SUCCESS: {new_size} bytes")
                return video_path
            else:
                # Не удалось исправить - возвращаем оригинал
                if os.path.exists(output_path):
                    os.remove(output_path)
                stderr = result.stderr.decode() if result.stderr else 'unknown'
                logger.warning(f"[FIX_VIDEO] FAILED: {stderr[:200]}")
                return None

        except Exception as e:
            logger.warning(f"[FIX_VIDEO] ERROR: {e}")
            return None

    def _format_error(self, error: str) -> str:
        """Форматирует сообщение об ошибке для пользователя"""
        error_lower = error.lower()

        # Словарь человеческих ошибок
        ERROR_MESSAGES = {
            "removed": "❌ Видео удалено",
            "terminated": "❌ Видео удалено",
            "private": "🔒 Это приватное видео",
            "unavailable": "❌ Видео недоступно",
            "not_available": "❌ Видео недоступно",
            "age_restricted": "🔞 Видео 18+",
            "copyright": "©️ Видео заблокировано по авторским правам",
            "live": "📺 Это прямая трансляция, не могу скачать",
            "streaming": "📺 Это прямая трансляция, не могу скачать",
            "members_only": "💎 Видео недоступно для скачивания",
            "members-only": "💎 Видео недоступно для скачивания",
            "subscription": "💎 Видео недоступно для скачивания",
            "timeout": "⏱ Превышено время ожидания, попробуй позже",
            "timed_out": "⏱ Сервер не отвечает, попробуй ещё раз",
            "connection_timed_out": "⏱ Сервер не отвечает, попробуй ещё раз",
            "not_found": "❌ Видео не найдено",
            "network": "🌐 Ошибка сети, попробуй позже",
            "connection": "🌐 Ошибка сети, попробуй позже",
            "geo_restricted": "❌ Видео недоступно в вашем регионе",
            "country": "❌ Видео недоступно в вашем регионе",
            "rate_limit": "⏱ Слишком много запросов, попробуй через минуту",
            "login_required": "Instagram требует авторизации для этого контента",
            "sign_in": "Instagram требует авторизации для этого контента",
            "authentication": "Instagram требует авторизации для этого контента",
        }

        # Проверяем каждый ключ ошибки
        for key, message in ERROR_MESSAGES.items():
            if key in error_lower.replace(" ", "_"):
                return message

        # Если ошибка не распознана - возвращаем первые 100 символов
        return error[:100] if len(error) > 100 else error

    async def cleanup(self, *paths: str):
        """Удаляет файлы после отправки"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Removed: {path}")
                except Exception as e:
                    logger.warning(f"Failed to remove {path}: {e}")

    async def download_photo(self, url: str) -> DownloadResult:
        """
        Скачивает фото по прямому URL или парсит Pinterest/Instagram

        Returns:
            DownloadResult с путём к файлу и is_photo=True
        """
        try:
            loop = asyncio.get_running_loop()

            # Определяем платформу
            if 'pinterest' in url or 'pin.it' in url:
                result = await asyncio.wait_for(
                    loop.run_in_executor(_executor, self._download_pinterest_photo, url),
                    timeout=DOWNLOAD_TIMEOUT
                )
            else:
                # Прямое скачивание по URL
                result = await asyncio.wait_for(
                    loop.run_in_executor(_executor, self._download_direct_photo, url),
                    timeout=DOWNLOAD_TIMEOUT
                )

            return result

        except asyncio.TimeoutError:
            return DownloadResult(
                success=False,
                error=f"Таймаут загрузки ({DOWNLOAD_TIMEOUT} сек)"
            )
        except Exception as e:
            logger.exception(f"Photo download error: {e}")
            return DownloadResult(
                success=False,
                error=str(e)[:100]
            )

    def _download_pinterest_photo(self, url: str) -> DownloadResult:
        """Скачивает фото из Pinterest"""
        try:
            # Загружаем страницу
            response = curl_requests.get(url, impersonate='chrome', timeout=30)
            response.raise_for_status()

            image_url = None

            # Способ 1: og:image (самый надёжный)
            og_patterns = [
                r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"',
                r'<meta[^>]*content="([^"]+)"[^>]*property="og:image"',
            ]
            for pattern in og_patterns:
                match = re.search(pattern, response.text)
                if match:
                    image_url = match.group(1)
                    logger.info(f"Pinterest og:image found: {image_url}")
                    break

            # Конвертируем 736x -> originals для максимального качества
            if image_url and '/736x/' in image_url:
                original_url = image_url.replace('/736x/', '/originals/')
                # Проверяем что originals существует
                try:
                    check = curl_requests.head(original_url, impersonate='chrome', timeout=10)
                    if check.status_code == 200:
                        image_url = original_url
                        logger.info(f"Upgraded to originals: {image_url}")
                except:
                    pass  # Используем 736x если originals недоступен

            # Способ 2: ищем в JSON данных (исключая placeholder d5/3b/01)
            if not image_url:
                all_originals = re.findall(
                    r'https://i\.pinimg\.com/originals/([a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]+\.(?:jpg|png|webp))',
                    response.text
                )
                # Фильтруем placeholder
                real_images = [img for img in all_originals if not img.startswith('d5/3b/01')]
                if real_images:
                    image_url = f"https://i.pinimg.com/originals/{real_images[0]}"
                    logger.info(f"Pinterest originals found: {image_url}")

            if not image_url:
                return DownloadResult(
                    success=False,
                    error="Не удалось найти изображение"
                )

            # Скачиваем изображение
            return self._download_direct_photo(image_url)

        except Exception as e:
            logger.exception(f"Pinterest photo error: {e}")
            return DownloadResult(
                success=False,
                error=f"Ошибка Pinterest: {str(e)[:50]}"
            )

    def _download_direct_photo(self, image_url: str) -> DownloadResult:
        """Скачивает фото по прямому URL"""
        try:
            response = curl_requests.get(image_url, impersonate='chrome', timeout=30)
            response.raise_for_status()

            # Определяем расширение
            content_type = response.headers.get('content-type', '')
            if 'png' in content_type or image_url.endswith('.png'):
                ext = 'png'
            elif 'webp' in content_type or image_url.endswith('.webp'):
                ext = 'webp'
            else:
                ext = 'jpg'

            # Сохраняем файл
            output_path = self._generate_filepath(ext)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            file_size = os.path.getsize(output_path)

            return DownloadResult(
                success=True,
                file_path=output_path,
                filename=f"photo.{ext}",
                file_size=file_size,
                is_photo=True,
                info=MediaInfo(title="photo", platform="pinterest")
            )

        except Exception as e:
            logger.exception(f"Direct photo download error: {e}")
            return DownloadResult(
                success=False,
                error=f"Ошибка скачивания: {str(e)[:50]}"
            )
