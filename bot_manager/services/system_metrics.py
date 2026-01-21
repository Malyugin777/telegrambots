"""
System Metrics Collector - записывает CPU/RAM/Disk метрики в Redis каждые 30 секунд.
Админ-панель на Aeza читает эти метрики для Ops Dashboard.
"""
import asyncio
import logging
import os
import shutil

import psutil
import redis.asyncio as redis

from shared.config import settings

logger = logging.getLogger(__name__)

# Интервал обновления метрик (секунды)
UPDATE_INTERVAL = 30

# TTL для метрик в Redis (секунды) - чуть больше интервала
METRICS_TTL = 60


async def collect_and_write_metrics(redis_client: redis.Redis):
    """Собирает системные метрики и записывает в Redis."""
    try:
        # CPU (average over 1 second)
        cpu_percent = psutil.cpu_percent(interval=1)

        # RAM
        ram = psutil.virtual_memory()
        ram_used_bytes = ram.used
        ram_total_bytes = ram.total
        ram_percent = ram.percent

        # Disk (root partition)
        disk = psutil.disk_usage('/')
        disk_used_bytes = disk.used
        disk_total_bytes = disk.total
        disk_percent = disk.percent

        # /tmp directory size
        tmp_path = '/tmp/downloads'
        tmp_used_bytes = 0
        if os.path.exists(tmp_path):
            for dirpath, dirnames, filenames in os.walk(tmp_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        tmp_used_bytes += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        pass

        # Write to Redis with TTL
        pipe = redis_client.pipeline()

        # CPU
        pipe.set("system:cpu_percent", str(cpu_percent), ex=METRICS_TTL)

        # RAM
        pipe.set("system:ram_percent", str(ram_percent), ex=METRICS_TTL)
        pipe.set("system:ram_used_bytes", str(ram_used_bytes), ex=METRICS_TTL)
        pipe.set("system:ram_total_bytes", str(ram_total_bytes), ex=METRICS_TTL)

        # Disk
        pipe.set("system:disk_percent", str(disk_percent), ex=METRICS_TTL)
        pipe.set("system:disk_used_bytes", str(disk_used_bytes), ex=METRICS_TTL)
        pipe.set("system:disk_total_bytes", str(disk_total_bytes), ex=METRICS_TTL)

        # /tmp
        pipe.set("system:tmp_used_bytes", str(tmp_used_bytes), ex=METRICS_TTL)

        await pipe.execute()

        logger.debug(
            f"System metrics written: CPU={cpu_percent}%, "
            f"RAM={ram_percent}% ({ram_used_bytes/1024/1024/1024:.1f}GB), "
            f"Disk={disk_percent}%, tmp={tmp_used_bytes/1024/1024:.1f}MB"
        )

    except Exception as e:
        logger.error(f"Error collecting system metrics: {e}")


async def system_metrics_loop():
    """Основной цикл сбора метрик."""
    logger.info(f"Starting system metrics collector (interval={UPDATE_INTERVAL}s)")

    # Connect to Redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        # Test connection
        await redis_client.ping()
        logger.info("System metrics collector connected to Redis")

        while True:
            await collect_and_write_metrics(redis_client)
            await asyncio.sleep(UPDATE_INTERVAL)

    except asyncio.CancelledError:
        logger.info("System metrics collector stopped")
    except Exception as e:
        logger.error(f"System metrics collector error: {e}")
    finally:
        await redis_client.close()


def start_system_metrics_task():
    """Запускает фоновую задачу сбора метрик."""
    asyncio.create_task(system_metrics_loop())
    logger.info("System metrics background task started")
