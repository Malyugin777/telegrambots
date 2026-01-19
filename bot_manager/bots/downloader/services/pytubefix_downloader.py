"""
pytubefix Downloader для YouTube

Бесплатный загрузчик с хорошей стабильностью
Версия: pytubefix 10.3.6+ (январь 2026)

Поддержка:
- YouTube Shorts
- Полные видео (любой длины)
- Качество: 720p (фиксированное)
"""
import os
import logging
import asyncio
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_BYTES = 2_000_000_000  # 2GB
DOWNLOAD_TIMEOUT = 1200  # 20 минут

_executor = ThreadPoolExecutor(max_workers=3)


@dataclass
class PytubeResult:
    """Результат скачивания через pytubefix"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    file_size: int = 0
    title: str = ""
    author: str = ""
    duration: int = 0
    error: Optional[str] = None


class PytubeDownloader:
    """
    Загрузчик YouTube через pytubefix

    Использование:
        downloader = PytubeDownloader()
        result = await downloader.download(url)
        if result.success:
            # result.file_path содержит путь к файлу
    """

    def __init__(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    async def get_video_info(self, url: str) -> PytubeResult:
        """
        Получить информацию о видео без скачивания

        Returns:
            PytubeResult с метаданными (title, author, duration)
        """
        try:
            from pytubefix import YouTube

            loop = asyncio.get_running_loop()

            def _get_info():
                try:
                    yt = YouTube(url)
                    return PytubeResult(
                        success=True,
                        title=yt.title or "video",
                        author=yt.author or "unknown",
                        duration=yt.length or 0
                    )
                except Exception as e:
                    logger.exception(f"[PYTUBEFIX] Get info error: {e}")
                    return PytubeResult(success=False, error=str(e)[:100])

            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, _get_info),
                timeout=30
            )
            return result

        except asyncio.TimeoutError:
            return PytubeResult(success=False, error="Info timeout")
        except ImportError:
            return PytubeResult(success=False, error="pytubefix not installed")
        except Exception as e:
            logger.exception(f"[PYTUBEFIX] Info error: {e}")
            return PytubeResult(success=False, error=str(e)[:100])

    async def download(self, url: str, quality: str = "720p") -> PytubeResult:
        """
        Скачать видео с YouTube

        Args:
            url: URL видео
            quality: Желаемое качество (по умолчанию 720p)

        Returns:
            PytubeResult с путём к файлу
        """
        try:
            from pytubefix import YouTube

            loop = asyncio.get_running_loop()

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._download_video,
                    url,
                    quality
                ),
                timeout=DOWNLOAD_TIMEOUT
            )

            return result

        except asyncio.TimeoutError:
            return PytubeResult(success=False, error=f"Download timeout ({DOWNLOAD_TIMEOUT}s)")
        except ImportError:
            return PytubeResult(success=False, error="pytubefix not installed")
        except Exception as e:
            logger.exception(f"[PYTUBEFIX] Download error: {e}")
            return PytubeResult(success=False, error=str(e)[:100])

    def _download_video(self, url: str, quality: str) -> PytubeResult:
        """Синхронное скачивание видео"""
        try:
            from pytubefix import YouTube

            logger.info(f"[PYTUBEFIX] Starting download: {url}, quality={quality}")

            yt = YouTube(url)

            # Информация о видео
            title = yt.title or "video"
            author = yt.author or "unknown"
            duration = yt.length or 0

            logger.info(f"[PYTUBEFIX] Video info: title='{title[:50]}', author='{author}', duration={duration}s")

            # Ищем поток с нужным качеством (progressive = видео+аудио вместе)
            stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4',
                res=quality
            ).first()

            # Если нет 720p, берём лучшее progressive
            if not stream:
                logger.warning(f"[PYTUBEFIX] {quality} not available, trying best progressive")
                stream = yt.streams.filter(
                    progressive=True,
                    file_extension='mp4'
                ).order_by('resolution').desc().first()

            # Если нет progressive, берём видео отдельно + аудио (потом надо объединить)
            if not stream:
                logger.warning(f"[PYTUBEFIX] No progressive stream, using adaptive")
                video_stream = yt.streams.filter(
                    adaptive=True,
                    file_extension='mp4',
                    only_video=True,
                    res=quality
                ).first()

                if not video_stream:
                    # Берём максимальное качество видео
                    video_stream = yt.streams.filter(
                        adaptive=True,
                        file_extension='mp4',
                        only_video=True
                    ).order_by('resolution').desc().first()

                if not video_stream:
                    return PytubeResult(success=False, error="No video stream found")

                stream = video_stream

            if not stream:
                return PytubeResult(success=False, error=f"No {quality} stream available")

            logger.info(f"[PYTUBEFIX] Selected stream: resolution={stream.resolution}, filesize={stream.filesize}")

            # Проверяем размер до скачивания
            file_size = stream.filesize or 0
            if file_size > MAX_FILE_SIZE_BYTES:
                size_mb = file_size // 1024 // 1024
                return PytubeResult(
                    success=False,
                    error=f"Video too large ({size_mb}MB > 2GB limit)"
                )

            # Скачиваем
            file_path = stream.download(output_path=DOWNLOAD_DIR)

            if not file_path or not os.path.exists(file_path):
                return PytubeResult(success=False, error="Download failed (no file)")

            actual_size = os.path.getsize(file_path)

            # Повторная проверка размера
            if actual_size > MAX_FILE_SIZE_BYTES:
                os.remove(file_path)
                size_mb = actual_size // 1024 // 1024
                return PytubeResult(
                    success=False,
                    error=f"Video too large ({size_mb}MB > 2GB limit)"
                )

            # Формируем безопасное имя файла
            safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()[:50]
            filename = f"{safe_title or 'video'}.mp4"

            logger.info(f"[PYTUBEFIX] Download success: size={actual_size}, path={file_path}")

            return PytubeResult(
                success=True,
                file_path=file_path,
                filename=filename,
                file_size=actual_size,
                title=title,
                author=author,
                duration=duration
            )

        except Exception as e:
            logger.exception(f"[PYTUBEFIX] Download error: {e}")
            return PytubeResult(success=False, error=str(e)[:100])

    async def cleanup(self, *paths: str):
        """Удалить файлы"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"[PYTUBEFIX] Cleaned up: {path}")
                except Exception as e:
                    logger.warning(f"[PYTUBEFIX] Cleanup error {path}: {e}")
