"""
pytubefix Downloader для YouTube

Бесплатный загрузчик с хорошей стабильностью
Версия: pytubefix 10.3.6+ (январь 2026)

Поддержка:
- YouTube Shorts
- Полные видео (любой длины)
- Качество: 720p (фиксированное)
- Adaptive streams: автоматическое объединение видео+аудио через ffmpeg
"""
import os
import logging
import asyncio
import subprocess
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
    thumbnail_url: Optional[str] = None  # URL превью с YouTube
    error: Optional[str] = None
    # Phase 7.0 Telemetry
    download_host: str = "googlevideo.com"  # pytubefix всегда качает с YouTube CDN


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

    def _get_video_codec(self, video_path: str) -> str:
        """Определить кодек видео через ffprobe"""
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=codec_name',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ], capture_output=True, text=True, timeout=5)

            codec = result.stdout.strip().lower()
            logger.info(f"[PYTUBEFIX] Detected codec: {codec}")
            return codec
        except Exception as e:
            logger.warning(f"[PYTUBEFIX] Failed to detect codec: {e}, assuming h264")
            return "h264"

    def _merge_video_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """
        Объединить видео и аудио через ffmpeg (БЕЗ перекодирования)

        Используем STREAM COPY + изменение метаданных (Вариант A+ - каноничный)
        - Мгновенная обработка (0.5 сек вместо 10 минут)
        - Нет потери качества (100% исходные пиксели)
        - Исправление aspect ratio через метаданные (SAR=1/1)
        - НЕ меняем геометрию кадра (без -aspect)

        Args:
            video_path: Путь к видео файлу
            audio_path: Путь к аудио файлу
            output_path: Путь к выходному файлу

        Returns:
            True если успешно, False если ошибка
        """
        try:
            logger.info(f"[PYTUBEFIX] Merging video+audio (stream copy, no re-encode): {output_path}")

            # Определяем кодек для правильного bsf (h264 vs hevc)
            codec = self._get_video_codec(video_path)

            # Выбираем правильный bitstream filter
            if 'hevc' in codec or 'h265' in codec:
                bsf = 'hevc_metadata=sample_aspect_ratio=1/1'
            elif 'vp9' in codec or 'vp8' in codec:
                bsf = None  # VP9/VP8 не поддерживают SAR metadata через bsf
            else:  # h264, avc1, etc
                bsf = 'h264_metadata=sample_aspect_ratio=1/1'

            # КАНОНИЧНОЕ РЕШЕНИЕ: Copy + Metadata (Variant A+)
            # Из deep research + GPT-рекомендации:
            # - НЕ трогаем DAR (без -aspect) - иначе 4:3 растянется до 16:9
            # - Только SAR=1/1 (квадратные пиксели) для Telegram
            # - faststart для корректного duration/preview
            cmd = [
                'ffmpeg',
                '-y',                            # Перезаписать если файл существует
                '-hide_banner',                  # Меньше мусора в логах
                '-loglevel', 'error',            # Только ошибки
                '-i', video_path,
                '-i', audio_path,
                '-map', '0:v:0',                 # Берём первый видео поток
                '-map', '1:a:0',                 # Берём первый аудио поток
                '-c', 'copy',                    # Копируем БЕЗ перекодирования
            ]

            # Добавляем bsf если кодек поддерживает
            if bsf:
                cmd.extend(['-bsf:v', bsf])

            cmd.extend([
                '-movflags', '+faststart',       # moov atom в начало → Telegram видит duration
                '-shortest',                     # Обрезать до самого короткого потока
                output_path
            ])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # 30 сек таймаут (copy быстрый)

            if result.returncode != 0:
                logger.error(f"[PYTUBEFIX] ffmpeg merge failed: {result.stderr}")
                return False

            logger.info(f"[PYTUBEFIX] Merge success (instant): {output_path}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("[PYTUBEFIX] ffmpeg merge timeout")
            return False
        except Exception as e:
            logger.exception(f"[PYTUBEFIX] Merge error: {e}")
            return False

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
            thumbnail_url = yt.thumbnail_url  # URL превью с YouTube

            logger.info(f"[PYTUBEFIX] Video info: title='{title[:50]}', author='{author}', duration={duration}s, thumb={thumbnail_url[:50] if thumbnail_url else 'none'}")

            # Логируем ВСЕ доступные потоки для анализа
            logger.info(f"[PYTUBEFIX] Available streams:")
            for s in yt.streams.filter(file_extension='mp4'):
                logger.info(f"  - {s.resolution} {'progressive' if s.includes_audio_track else 'adaptive'} "
                           f"{'video+audio' if s.includes_audio_track else 'video-only'} size={s.filesize}")

            # Переменные для adaptive
            audio_stream = None
            use_adaptive = False

            # Ищем поток с нужным качеством (progressive = видео+аудио вместо)
            progressive_stream = yt.streams.filter(
                progressive=True,
                file_extension='mp4',
                res=quality
            ).first()

            # Если есть progressive 720p - используем его
            if progressive_stream:
                logger.info(f"[PYTUBEFIX] Using progressive stream: {quality}")
                stream = progressive_stream

            else:
                # Нет progressive 720p - используем adaptive (видео отдельно + аудио)
                logger.info(f"[PYTUBEFIX] Progressive {quality} not available, using adaptive streams")

                # Ищем видео 720p adaptive
                video_stream = yt.streams.filter(
                    adaptive=True,
                    file_extension='mp4',
                    only_video=True,
                    res=quality
                ).first()

                # Если нет 720p, берём максимальное качество
                if not video_stream:
                    logger.warning(f"[PYTUBEFIX] {quality} adaptive not found, using best quality")
                    video_stream = yt.streams.filter(
                        adaptive=True,
                        file_extension='mp4',
                        only_video=True
                    ).order_by('resolution').desc().first()

                if not video_stream:
                    return PytubeResult(success=False, error="No video stream found")

                # Ищем лучший аудио поток
                audio_stream = yt.streams.filter(
                    adaptive=True,
                    only_audio=True
                ).order_by('abr').desc().first()

                if not audio_stream:
                    return PytubeResult(success=False, error="No audio stream found")

                stream = video_stream
                use_adaptive = True

            if not stream:
                return PytubeResult(success=False, error=f"No {quality} stream available")

            logger.info(f"[PYTUBEFIX] Selected stream: resolution={stream.resolution}, filesize={stream.filesize}, adaptive={use_adaptive}")

            # Проверяем размер до скачивания
            video_size = stream.filesize or 0
            audio_size = audio_stream.filesize if use_adaptive else 0
            estimated_size = video_size + audio_size

            if estimated_size > MAX_FILE_SIZE_BYTES:
                size_mb = estimated_size // 1024 // 1024
                return PytubeResult(
                    success=False,
                    error=f"Video too large ({size_mb}MB > 2GB limit)"
                )

            # Скачиваем
            if use_adaptive:
                # Adaptive: скачиваем видео + аудио, мержим
                logger.info(f"[PYTUBEFIX] Downloading adaptive streams: video={stream.resolution}, audio={audio_stream.abr}")

                # Скачиваем видео
                video_path = stream.download(output_path=DOWNLOAD_DIR, filename_prefix="video_")
                if not video_path or not os.path.exists(video_path):
                    return PytubeResult(success=False, error="Video download failed")

                # Скачиваем аудио
                audio_path = audio_stream.download(output_path=DOWNLOAD_DIR, filename_prefix="audio_")
                if not audio_path or not os.path.exists(audio_path):
                    os.remove(video_path)
                    return PytubeResult(success=False, error="Audio download failed")

                # Мержим через ffmpeg
                import uuid
                output_filename = f"merged_{uuid.uuid4().hex[:12]}.mp4"
                file_path = os.path.join(DOWNLOAD_DIR, output_filename)

                merge_success = self._merge_video_audio(video_path, audio_path, file_path)

                # Удаляем исходники
                try:
                    os.remove(video_path)
                    os.remove(audio_path)
                except:
                    pass

                if not merge_success:
                    return PytubeResult(success=False, error="ffmpeg merge failed")

                if not os.path.exists(file_path):
                    return PytubeResult(success=False, error="Merge output not found")

                # SAR/DAR уже исправлены через ffmpeg metadata в merge

            else:
                # Progressive: скачиваем как обычно
                file_path = stream.download(output_path=DOWNLOAD_DIR)
                if not file_path or not os.path.exists(file_path):
                    return PytubeResult(success=False, error="Download failed (no file)")

                # Progressive видео отправляются как есть + width/height в sendVideo (Issue #468)

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
                duration=duration,
                thumbnail_url=thumbnail_url
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
