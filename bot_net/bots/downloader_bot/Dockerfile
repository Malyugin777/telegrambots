FROM python:3.12-slim

WORKDIR /app

# Установка системных зависимостей
# ffmpeg — для извлечения аудио и конвертации
# yt-dlp требует ffmpeg для постобработки
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создаём папку для загрузок
RUN mkdir -p /tmp/downloads && chmod 777 /tmp/downloads

# Копируем requirements
COPY bot_net/requirements.txt /app/requirements.txt

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем yt-dlp отдельно (последняя версия)
RUN pip install --no-cache-dir --upgrade yt-dlp

# Копируем общий код
COPY shared /app/shared

# Копируем код ботов
COPY bot_net /app/bot_net

# Устанавливаем Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Папка для загрузок
ENV DOWNLOAD_PATH=/tmp/downloads

# Запуск downloader bot
CMD ["python", "-m", "bot_net.bots.downloader_bot.main"]
