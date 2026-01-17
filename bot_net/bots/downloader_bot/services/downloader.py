"""
Сервис скачивания видео через yt-dlp

Поддерживаемые платформы:
- TikTok (vm.tiktok.com, tiktok.com) — без водяного знака
- Instagram Reels (instagram.com/reel/, instagram.com/p/)
- YouTube Shorts (youtube.com/shorts/)
- Pinterest (pin.it, pinterest.com)
"""
import os
import asyncio
import logging
import uuid
import shutil
from dataclasses import dataclass, field
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

logger = logging.getLogger(__name__)

# Константы
DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 60  # секунд
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

    def _get_video_options(self, output_path: str) -> dict:
        """
        Опции yt-dlp для скачивания видео

        Args:
            output_path: Путь для сохранения файла
        """
        return {
            # Основные настройки
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,

            # Формат: лучшее видео до 50MB, предпочитаем готовый mp4
            # Приоритет: готовый mp4 > объединение видео+аудио
            'format': (
                'best[ext=mp4][filesize<50M]/'
                'best[filesize<50M]/'
                'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo+bestaudio/best'
            ),
            'merge_output_format': 'mp4',

            # Путь сохранения
            'outtmpl': output_path,

            # Сеть
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'nocheckcertificate': True,
            'geo_bypass': True,

            # НЕ конвертировать/перекодировать — сохраняем оригинал
            'postprocessor_args': {
                'ffmpeg': ['-c', 'copy']  # Копируем без перекодирования
            },

            # TikTok: скачивание без водяного знака
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api22-normal-c-useast2a.tiktokv.com',
                    'webpage_download': True,
                }
            },

            # Дополнительно
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            },
        }

    def _get_audio_options(self, output_path: str) -> dict:
        """
        Опции yt-dlp для извлечения аудио

        Args:
            output_path: Путь для сохранения файла (без расширения)
        """
        return {
            # Основные настройки
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,

            # Формат: лучшее аудио
            'format': 'bestaudio/best',

            # Путь сохранения
            'outtmpl': output_path,

            # Постобработка: конвертация в MP3 320kbps
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': AUDIO_BITRATE,
            }],

            # Сеть
            'socket_timeout': 30,
            'retries': 3,
            'nocheckcertificate': True,
            'geo_bypass': True,

            # TikTok
            'extractor_args': {
                'tiktok': {
                    'api_hostname': 'api22-normal-c-useast2a.tiktokv.com',
                }
            },
        }

    def _get_info_options(self) -> dict:
        """Опции для получения информации без скачивания"""
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'socket_timeout': 15,
            'nocheckcertificate': True,
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
        # Убираем недопустимые символы
        safe = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
        safe = safe[:50] if safe else "video"
        return f"{safe}.{ext}"

    async def download(self, url: str) -> DownloadResult:
        """
        Скачивает видео по URL

        Args:
            url: Ссылка на видео (TikTok, Instagram, YouTube, Pinterest)

        Returns:
            DownloadResult с путём к файлу или ошибкой
        """
        output_path = self._generate_filepath("mp4")
        opts = self._get_video_options(output_path)

        try:
            loop = asyncio.get_running_loop()

            # Скачиваем в отдельном потоке с таймаутом
            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._download_sync, url, opts),
                timeout=DOWNLOAD_TIMEOUT
            )

            if not result.success:
                return result

            # Проверяем размер файла
            if result.file_size > MAX_FILE_SIZE_BYTES:
                await self.cleanup(result.file_path)
                return DownloadResult(
                    success=False,
                    error=f"Файл слишком большой ({result.file_size // 1024 // 1024}MB > {MAX_FILE_SIZE_MB}MB)"
                )

            return result

        except asyncio.TimeoutError:
            # Удаляем частично скачанный файл
            await self.cleanup(output_path)
            return DownloadResult(
                success=False,
                error=f"Таймаут загрузки ({DOWNLOAD_TIMEOUT} сек)"
            )
        except Exception as e:
            logger.exception(f"Download error for {url}: {e}")
            await self.cleanup(output_path)
            return DownloadResult(
                success=False,
                error=self._format_error(str(e))
            )

    async def download_audio(self, url: str) -> DownloadResult:
        """
        Скачивает и извлекает аудио из видео (MP3 320kbps)

        Args:
            url: Ссылка на видео

        Returns:
            DownloadResult с путём к MP3 файлу
        """
        # Генерируем путь без расширения (yt-dlp добавит .mp3)
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

            # Проверяем размер
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

    async def extract_audio(self, video_path: str) -> DownloadResult:
        """
        Извлекает аудио из уже скачанного видео

        Args:
            video_path: Путь к видеофайлу

        Returns:
            DownloadResult с путём к MP3 файлу
        """
        if not os.path.exists(video_path):
            return DownloadResult(
                success=False,
                error="Видеофайл не найден"
            )

        output_path = video_path.rsplit('.', 1)[0] + ".mp3"

        try:
            loop = asyncio.get_running_loop()

            def _extract():
                import subprocess
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-vn',  # Без видео
                    '-acodec', 'libmp3lame',
                    '-ab', f'{AUDIO_BITRATE}k',
                    '-ar', '44100',
                    '-y',  # Перезаписать
                    output_path
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                return result.returncode == 0

            success = await asyncio.wait_for(
                loop.run_in_executor(_executor, _extract),
                timeout=DOWNLOAD_TIMEOUT
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

        except Exception as e:
            logger.exception(f"Audio extraction error: {e}")
            return DownloadResult(
                success=False,
                error=str(e)[:100]
            )

    def _download_sync(self, url: str, opts: dict, is_audio: bool = False) -> DownloadResult:
        """
        Синхронная загрузка (выполняется в thread pool)

        Args:
            url: URL для скачивания
            opts: Опции yt-dlp
            is_audio: Это аудио загрузка
        """
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Скачиваем
                info = ydl.extract_info(url, download=True)

                if not info:
                    return DownloadResult(
                        success=False,
                        error="Не удалось получить информацию о видео"
                    )

                # Получаем путь к файлу
                file_path = self._find_downloaded_file(info, opts, is_audio)

                if not file_path or not os.path.exists(file_path):
                    return DownloadResult(
                        success=False,
                        error="Файл не найден после скачивания"
                    )

                # Получаем информацию
                media_info = self._extract_info(info)
                file_size = os.path.getsize(file_path)
                ext = "mp3" if is_audio else "mp4"
                filename = self._sanitize_filename(media_info.title, ext)

                return DownloadResult(
                    success=True,
                    file_path=file_path,
                    filename=filename,
                    info=media_info,
                    file_size=file_size
                )

        except yt_dlp.utils.DownloadError as e:
            return DownloadResult(
                success=False,
                error=self._format_error(str(e))
            )
        except Exception as e:
            logger.exception(f"yt-dlp sync error: {e}")
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
            # Убираем %(ext)s если есть
            base = template.replace('.%(ext)s', '').replace('%(ext)s', '')

            # Пробуем разные расширения
            extensions = ['mp3'] if is_audio else ['mp4', 'webm', 'mkv']
            for ext in extensions:
                path = f"{base}.{ext}"
                if os.path.exists(path):
                    return path

        return None

    def _format_error(self, error: str) -> str:
        """Форматирует сообщение об ошибке для пользователя"""
        error_lower = error.lower()

        if "private" in error_lower:
            return "Видео приватное"
        elif "unavailable" in error_lower or "not available" in error_lower:
            return "Видео недоступно"
        elif "age" in error_lower:
            return "Видео с ограничением по возрасту"
        elif "copyright" in error_lower:
            return "Видео заблокировано из-за авторских прав"
        elif "geo" in error_lower or "country" in error_lower:
            return "Видео недоступно в вашем регионе"
        elif "login" in error_lower or "sign in" in error_lower:
            return "Требуется авторизация"
        elif "404" in error or "not found" in error_lower:
            return "Видео не найдено"
        elif "rate limit" in error_lower:
            return "Слишком много запросов, попробуйте позже"
        else:
            # Обрезаем длинные ошибки
            return error[:150] if len(error) > 150 else error

    async def get_info(self, url: str) -> Optional[MediaInfo]:
        """
        Получает информацию о видео без скачивания

        Args:
            url: URL видео

        Returns:
            MediaInfo или None
        """
        opts = self._get_info_options()

        try:
            loop = asyncio.get_running_loop()

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.wait_for(
                loop.run_in_executor(_executor, _extract),
                timeout=15
            )

            if info:
                return self._extract_info(info)
            return None

        except Exception as e:
            logger.warning(f"Failed to get info for {url}: {e}")
            return None

    async def cleanup(self, *paths: str):
        """
        Удаляет файлы после отправки

        Args:
            *paths: Пути к файлам для удаления
        """
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"Removed: {path}")
                except Exception as e:
                    logger.warning(f"Failed to remove {path}: {e}")

    @staticmethod
    async def cleanup_old_files(max_age_seconds: int = 3600):
        """
        Очищает старые файлы в папке загрузок

        Args:
            max_age_seconds: Максимальный возраст файла в секундах
        """
        import time

        if not os.path.exists(DOWNLOAD_DIR):
            return

        now = time.time()
        count = 0

        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    file_age = now - os.path.getmtime(filepath)
                    if file_age > max_age_seconds:
                        os.remove(filepath)
                        count += 1
            except Exception as e:
                logger.warning(f"Failed to clean {filepath}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} old files from {DOWNLOAD_DIR}")
