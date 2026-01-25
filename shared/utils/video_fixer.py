"""
Утилита для исправления SAR/DAR в видео файлах.

Многие платформы (TikTok, Pinterest, YouTube, Instagram) отдают видео
с неправильными метаданными Sample Aspect Ratio (SAR).
iOS Telegram игнорирует SAR и рендерит пиксели напрямую, поэтому
нужно РЕАЛЬНО масштабировать видео, а не только менять метаданные.

Также содержит ensure_faststart() для перемещения moov atom в начало файла,
что критически важно для корректного отображения duration в Telegram.
"""
import os
import logging
import subprocess
import json
import uuid
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "/tmp/downloads"


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    """
    Извлекает размеры видео через ffprobe.

    Args:
        video_path: Путь к видео файлу

    Returns:
        Кортеж (width, height). Если не удалось определить, возвращает (0, 0)
    """
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'json', video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)

        data = json.loads(result.stdout.strip())
        streams = data.get('streams', [])
        if not streams:
            logger.warning(f"[GET_DIMENSIONS] No streams found in {video_path}")
            return (0, 0)

        stream = streams[0]
        width = stream.get('width', 0)
        height = stream.get('height', 0)

        logger.info(f"[GET_DIMENSIONS] {video_path}: {width}x{height}")
        return (width, height)

    except Exception as e:
        logger.warning(f"[GET_DIMENSIONS] Error for {video_path}: {e}")
        return (0, 0)


def get_video_duration(video_path: str) -> int:
    """
    Извлекает длительность видео через ffprobe.

    Args:
        video_path: Путь к видео файлу

    Returns:
        Длительность в секундах. Если не удалось определить, возвращает 0
    """
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'format=duration',
            '-of', 'json', video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)

        data = json.loads(result.stdout.strip())
        duration_str = data.get('format', {}).get('duration', '0')
        duration = int(float(duration_str))

        logger.info(f"[GET_DURATION] {video_path}: {duration}s")
        return duration

    except Exception as e:
        logger.warning(f"[GET_DURATION] Error for {video_path}: {e}")
        return 0


def ensure_faststart(video_path: str) -> bool:
    """
    Гарантирует что moov atom находится в начале файла (faststart).

    Это КРИТИЧЕСКИ важно для корректного отображения duration/preview в Telegram.
    Выполняется через stream copy (без перекодирования) - очень быстро.

    Логика:
    - Проверяем позицию moov через ffprobe
    - Если moov уже в начале - ничего не делаем
    - Если moov в конце - remux с +faststart

    Args:
        video_path: Путь к видео файлу

    Returns:
        True если faststart применён или уже был, False при ошибке
    """
    try:
        # Проверяем существует ли файл
        if not os.path.exists(video_path):
            logger.warning(f"[FASTSTART] File not found: {video_path}")
            return False

        # Проверяем позицию moov через ffprobe
        # Если файл "streamable" - moov уже в начале
        probe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format_tags=creation_time',
            '-show_entries', 'format=duration',
            '-of', 'json', video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)

        # Простая проверка: если ffprobe быстро вернул duration - файл стримится нормально
        # Более точная проверка требует анализа atoms, но для наших целей достаточно remux

        output_path = video_path.rsplit('.', 1)[0] + "_faststart.mp4"

        # Remux с faststart (stream copy, без перекодирования)
        # -fflags +genpts помогает с кривыми таймингами (PTS/DTS)
        faststart_cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-fflags', '+genpts',
            '-i', video_path,
            '-map', '0',
            '-c', 'copy',
            '-movflags', '+faststart',
            output_path
        ]

        result = subprocess.run(faststart_cmd, capture_output=True, timeout=60)

        if result.returncode == 0 and os.path.exists(output_path):
            # Заменяем оригинал
            os.remove(video_path)
            os.rename(output_path, video_path)
            new_size = os.path.getsize(video_path)
            logger.info(f"[FASTSTART] SUCCESS: {video_path}, size={new_size}")
            return True
        else:
            # Не удалось - удаляем временный файл
            if os.path.exists(output_path):
                os.remove(output_path)
            stderr = result.stderr.decode() if result.stderr else 'unknown'
            logger.warning(f"[FASTSTART] FAILED: {stderr[:200]}")
            return False

    except Exception as e:
        logger.warning(f"[FASTSTART] ERROR: {e}")
        return False


def download_thumbnail(thumbnail_url: str) -> Optional[str]:
    """
    Скачивает и ужимает thumbnail для Telegram.

    Telegram требует:
    - JPEG формат
    - До ~320px по длинной стороне
    - Небольшой вес (<200KB)

    Args:
        thumbnail_url: URL превью (например с YouTube)

    Returns:
        Путь к локальному thumbnail файлу или None при ошибке
    """
    if not thumbnail_url:
        return None

    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Генерируем уникальное имя
        unique_id = uuid.uuid4().hex[:12]
        temp_path = os.path.join(DOWNLOAD_DIR, f"thumb_raw_{unique_id}.jpg")
        output_path = os.path.join(DOWNLOAD_DIR, f"thumb_{unique_id}.jpg")

        # Скачиваем thumbnail
        logger.info(f"[THUMBNAIL] Downloading: {thumbnail_url[:80]}")
        urllib.request.urlretrieve(thumbnail_url, temp_path)

        if not os.path.exists(temp_path):
            logger.warning(f"[THUMBNAIL] Download failed")
            return None

        # Ужимаем до 320px по длинной стороне через ffmpeg
        # scale='min(320,iw)':-2 - если меньше 320 - не увеличиваем, -2 для чётной высоты
        resize_cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-i', temp_path,
            '-vf', "scale='min(320,iw)':-2",
            '-q:v', '5',  # JPEG качество (2-31, меньше = лучше)
            output_path
        ]

        result = subprocess.run(resize_cmd, capture_output=True, timeout=10)

        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if result.returncode == 0 and os.path.exists(output_path):
            thumb_size = os.path.getsize(output_path)
            logger.info(f"[THUMBNAIL] SUCCESS: {output_path}, size={thumb_size}")
            return output_path
        else:
            stderr = result.stderr.decode() if result.stderr else 'unknown'
            logger.warning(f"[THUMBNAIL] Resize failed: {stderr[:100]}")
            return None

    except Exception as e:
        logger.warning(f"[THUMBNAIL] ERROR: {e}")
        return None


def generate_thumbnail_from_video(video_path: str, timestamp: float = 1.0) -> Optional[str]:
    """
    Генерирует thumbnail из кадра видео.

    Используется для вертикальных видео (Shorts, TikTok, Reels),
    где YouTube/платформа даёт горизонтальный thumbnail.

    Args:
        video_path: Путь к видео файлу
        timestamp: Время в секундах для извлечения кадра (default: 1.0)

    Returns:
        Путь к thumbnail файлу или None при ошибке
    """
    if not video_path or not os.path.exists(video_path):
        return None

    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        unique_id = uuid.uuid4().hex[:12]
        output_path = os.path.join(DOWNLOAD_DIR, f"thumb_{unique_id}.jpg")

        # Извлекаем кадр и ресайзим до 320px по длинной стороне
        cmd = [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', str(timestamp),  # Seek до timestamp
            '-i', video_path,
            '-vframes', '1',  # Только 1 кадр
            '-vf', "scale='min(320,iw)':'min(320,ih)':force_original_aspect_ratio=decrease",
            '-q:v', '5',  # JPEG качество
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=10)

        if result.returncode == 0 and os.path.exists(output_path):
            thumb_size = os.path.getsize(output_path)
            logger.info(f"[THUMBNAIL] Generated from video: {output_path}, size={thumb_size}")
            return output_path
        else:
            stderr = result.stderr.decode() if result.stderr else 'unknown'
            logger.warning(f"[THUMBNAIL] Generate from video failed: {stderr[:100]}")
            return None

    except Exception as e:
        logger.warning(f"[THUMBNAIL] Generate from video ERROR: {e}")
        return None


def fix_video(video_path: str) -> Optional[str]:
    """
    Исправляет SAR/DAR для ВСЕХ видео (TikTok, Pinterest, YouTube, Instagram).
    ЯВНО пересчитывает пиксели для правильного отображения.

    Многие платформы отдают HEVC/H264 с неправильными метаданными SAR/DAR.
    iOS Telegram игнорирует SAR и рендерит пиксели напрямую — поэтому нужно
    РЕАЛЬНО масштабировать видео, а не только менять метаданные.

    Логика:
    - SAR = 1:1 и H.264 → ничего не делаем
    - SAR ≠ 1:1 → вычисляем новые размеры и масштабируем пиксели

    Args:
        video_path: Путь к видео файлу

    Returns:
        Путь к исправленному файлу или None если исправление не требовалось
    """
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
