"""
Сервис скачивания видео через yt-dlp
"""
import os
import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    """Результат скачивания"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    duration: Optional[int] = None
    error: Optional[str] = None


class VideoDownloader:
    """Скачивание видео через yt-dlp"""

    def __init__(self, config):
        self.config = config
        self.download_path = config.download_path

    def _get_yt_dlp_options(self, extract_audio: bool = False) -> dict:
        """Опции для yt-dlp"""
        unique_id = str(uuid.uuid4())[:8]

        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'extractor_args': {
                'tiktok': {'webpage_download': 'true'},
            },
        }

        if extract_audio:
            # Извлекаем только аудио
            base_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self.download_path, f'{unique_id}.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            # Скачиваем видео
            base_opts.update({
                'format': 'best[ext=mp4]/best',
                'outtmpl': os.path.join(self.download_path, f'{unique_id}.%(ext)s'),
                'merge_output_format': 'mp4',
            })

        return base_opts

    async def download(self, url: str, extract_audio: bool = False) -> DownloadResult:
        """
        Скачивает видео/аудио

        Args:
            url: URL видео
            extract_audio: Извлечь только аудио

        Returns:
            DownloadResult
        """
        opts = self._get_yt_dlp_options(extract_audio)

        try:
            # Запускаем в executor чтобы не блокировать event loop
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._download_sync, url, opts, extract_audio),
                timeout=120  # 2 минуты таймаут
            )
            return result

        except asyncio.TimeoutError:
            return DownloadResult(
                success=False,
                error="Таймаут загрузки (>2 мин)"
            )
        except Exception as e:
            logger.exception(f"Download error: {e}")
            return DownloadResult(
                success=False,
                error=str(e)[:200]
            )

    def _download_sync(self, url: str, opts: dict, extract_audio: bool) -> DownloadResult:
        """Синхронная загрузка (запускается в executor)"""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Получаем информацию
                info = ydl.extract_info(url, download=True)

                if not info:
                    return DownloadResult(
                        success=False,
                        error="Не удалось получить информацию о видео"
                    )

                # Проверяем длительность
                duration = info.get('duration', 0)
                if duration > self.config.max_video_duration:
                    return DownloadResult(
                        success=False,
                        error=f"Видео слишком длинное ({duration}s > {self.config.max_video_duration}s)"
                    )

                # Находим скачанный файл
                if extract_audio:
                    ext = 'mp3'
                else:
                    ext = info.get('ext', 'mp4')

                # Получаем путь к файлу
                if 'requested_downloads' in info and info['requested_downloads']:
                    file_path = info['requested_downloads'][0].get('filepath')
                else:
                    # Пробуем найти файл
                    template = opts['outtmpl']
                    base_path = template.rsplit('.', 1)[0]
                    for possible_ext in ['mp4', 'mp3', 'webm', 'm4a']:
                        possible_path = f"{base_path}.{possible_ext}"
                        if os.path.exists(possible_path):
                            file_path = possible_path
                            break
                    else:
                        return DownloadResult(
                            success=False,
                            error="Файл не найден после скачивания"
                        )

                if not os.path.exists(file_path):
                    return DownloadResult(
                        success=False,
                        error="Файл не найден после скачивания"
                    )

                # Формируем имя файла
                title = info.get('title', 'video')[:50]
                author = info.get('uploader', info.get('channel', 'unknown'))[:30]

                safe_title = "".join(c for c in title if c.isalnum() or c in ' -_').strip()
                filename = f"{safe_title}.{ext}"

                return DownloadResult(
                    success=True,
                    file_path=file_path,
                    filename=filename,
                    title=title,
                    author=author,
                    duration=duration
                )

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            # Упрощаем сообщение об ошибке
            if "Private video" in error_msg:
                error_msg = "Видео приватное"
            elif "Video unavailable" in error_msg:
                error_msg = "Видео недоступно"
            elif "age" in error_msg.lower():
                error_msg = "Видео с ограничением по возрасту"

            return DownloadResult(
                success=False,
                error=error_msg[:200]
            )
        except Exception as e:
            logger.exception(f"yt-dlp error: {e}")
            return DownloadResult(
                success=False,
                error=str(e)[:200]
            )

    async def get_info(self, url: str) -> Optional[dict]:
        """
        Получает информацию о видео без скачивания

        Args:
            url: URL видео

        Returns:
            Информация о видео или None
        """
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'socket_timeout': 15,
        }

        try:
            loop = asyncio.get_event_loop()

            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.wait_for(
                loop.run_in_executor(None, _extract),
                timeout=30
            )
            return info

        except Exception as e:
            logger.warning(f"Failed to get info for {url}: {e}")
            return None
