"""
Instaloader для Instagram

Бесплатный загрузчик с полным функционалом
Версия: instaloader 4.15+ (январь 2026)

Поддержка (без логина):
- Публичные посты
- Reels
- Карусели
- Фото

Не поддерживается без логина:
- Приватные аккаунты
- Stories (требуют логин)
"""
import os
import re
import logging
import asyncio
import shutil
from dataclasses import dataclass
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "/tmp/downloads"
MAX_FILE_SIZE_BYTES = 2_000_000_000  # 2GB
DOWNLOAD_TIMEOUT = 600  # 10 минут для Instagram

_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class InstaloaderFile:
    """Скачанный файл"""
    file_path: str
    filename: str
    file_size: int
    is_photo: bool


@dataclass
class InstaloaderResult:
    """Результат скачивания через instaloader"""
    success: bool
    files: List[InstaloaderFile] = None
    title: str = ""
    author: str = ""
    is_carousel: bool = False
    error: Optional[str] = None


class InstaloaderDownloader:
    """
    Загрузчик Instagram через instaloader

    Работает БЕЗ логина для публичного контента:
    - Посты
    - Reels
    - Карусели (несколько фото/видео)

    Использование:
        downloader = InstaloaderDownloader()
        result = await downloader.download(url)
        if result.success:
            # result.files содержит список файлов
    """

    def __init__(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    def _extract_shortcode(self, url: str) -> Optional[str]:
        """
        Извлечь shortcode из Instagram URL

        Примеры:
        - https://www.instagram.com/p/ABC123/
        - https://www.instagram.com/reel/ABC123/
        - https://instagram.com/p/ABC123/
        """
        patterns = [
            r'instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)',
            r'instagr\.am/p/([A-Za-z0-9_-]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    async def download(self, url: str) -> InstaloaderResult:
        """
        Скачать пост/reel с Instagram

        Args:
            url: URL поста/reel

        Returns:
            InstaloaderResult со списком файлов (может быть карусель)
        """
        shortcode = self._extract_shortcode(url)

        if not shortcode:
            return InstaloaderResult(
                success=False,
                error="Invalid Instagram URL (cannot extract shortcode)"
            )

        logger.info(f"[INSTALOADER] Starting download: shortcode={shortcode}")

        try:
            loop = asyncio.get_running_loop()

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    self._download_post,
                    shortcode
                ),
                timeout=DOWNLOAD_TIMEOUT
            )

            return result

        except asyncio.TimeoutError:
            return InstaloaderResult(success=False, error=f"Download timeout ({DOWNLOAD_TIMEOUT}s)")
        except ImportError:
            return InstaloaderResult(success=False, error="instaloader not installed")
        except Exception as e:
            logger.exception(f"[INSTALOADER] Download error: {e}")
            return InstaloaderResult(success=False, error=str(e)[:100])

    def _download_post(self, shortcode: str) -> InstaloaderResult:
        """Синхронное скачивание поста"""
        temp_dir = None

        try:
            import instaloader

            # Создаём временную папку для скачивания
            temp_dir = os.path.join(DOWNLOAD_DIR, f"insta_{shortcode}")
            os.makedirs(temp_dir, exist_ok=True)

            # Настраиваем instaloader (без логина)
            L = instaloader.Instaloader(
                download_videos=True,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                dirname_pattern=temp_dir,
                filename_pattern="{shortcode}",
            )

            logger.info(f"[INSTALOADER] Fetching post: shortcode={shortcode}")

            # Получаем пост
            post = instaloader.Post.from_shortcode(L.context, shortcode)

            # Проверяем доступность (is_private может не существовать, проверяем owner_profile)
            try:
                # Пробуем получить доступ к метаданным (если приватное - упадет)
                _ = post.caption
            except Exception as e:
                if "login" in str(e).lower() or "private" in str(e).lower():
                    return InstaloaderResult(
                        success=False,
                        error="Private content (login required)"
                    )
                # Другая ошибка - пробрасываем дальше
                raise

            # Метаданные
            title = post.caption[:100] if post.caption else "instagram_media"
            author = post.owner_username or "unknown"

            logger.info(f"[INSTALOADER] Post info: author='{author}', caption='{title[:50]}', carousel={post.typename == 'GraphSidecar'}")

            # Скачиваем
            L.download_post(post, target=temp_dir)

            # Собираем скачанные файлы
            files = []

            # Ищем файлы в папке
            for file_path in Path(temp_dir).iterdir():
                if file_path.is_file():
                    # Пропускаем txt/json метаданные
                    if file_path.suffix.lower() in ['.txt', '.json', '.json.xz']:
                        continue

                    file_size = os.path.getsize(file_path)

                    # Проверяем размер
                    if file_size > MAX_FILE_SIZE_BYTES:
                        size_mb = file_size // 1024 // 1024
                        # Пропускаем слишком большие, но продолжаем со следующими
                        logger.warning(f"[INSTALOADER] File too large ({size_mb}MB): {file_path.name}")
                        continue

                    # Определяем тип
                    is_photo = file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']

                    # Перемещаем в основную папку
                    new_filename = f"{shortcode}_{len(files)}{file_path.suffix}"
                    new_path = os.path.join(DOWNLOAD_DIR, new_filename)
                    shutil.move(str(file_path), new_path)

                    files.append(InstaloaderFile(
                        file_path=new_path,
                        filename=new_filename,
                        file_size=file_size,
                        is_photo=is_photo
                    ))

                    logger.info(f"[INSTALOADER] Downloaded: {new_filename}, size={file_size}, is_photo={is_photo}")

            # Очищаем временную папку
            shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir = None

            if not files:
                return InstaloaderResult(
                    success=False,
                    error="No media files downloaded"
                )

            is_carousel = len(files) > 1

            logger.info(f"[INSTALOADER] Success: {len(files)} files, carousel={is_carousel}")

            return InstaloaderResult(
                success=True,
                files=files,
                title=title,
                author=author,
                is_carousel=is_carousel
            )

        except Exception as e:
            error_str = str(e).lower()

            # Обрабатываем специфичные ошибки
            if "login" in error_str or "private" in error_str:
                error_msg = "Private content (login required)"
            elif "not found" in error_str:
                error_msg = "Post not found"
            elif "rate" in error_str or "limit" in error_str:
                error_msg = "Rate limit (try again later)"
            else:
                error_msg = str(e)[:100]

            logger.exception(f"[INSTALOADER] Download error: {e}")
            return InstaloaderResult(success=False, error=error_msg)

        finally:
            # Очистка временной папки при ошибке
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    async def cleanup(self, *paths: str):
        """Удалить файлы"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.debug(f"[INSTALOADER] Cleaned up: {path}")
                except Exception as e:
                    logger.warning(f"[INSTALOADER] Cleanup error {path}: {e}")
