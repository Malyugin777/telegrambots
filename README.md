# TelegramBots

Система управления Telegram-ботами с веб-админкой.

## SaveNinja Bot (@SaveNinja_bot)

Скачивание медиа из социальных сетей с автоматической обработкой для идеального отображения в Telegram.

### Поддерживаемые платформы

| Платформа | Форматы | Движок | Лимит |
|-----------|---------|--------|-------|
| **Instagram** | Фото, видео, Reels, карусели, истории | RapidAPI | 50MB |
| **Pinterest** | Фото и видео (включая pin.it) | yt-dlp | 50MB |
| **TikTok** | Видео без водяного знака | yt-dlp | 50MB |
| **YouTube Shorts** | Короткие видео (<5 мин) | pytubefix | 50MB |
| **YouTube Full** | Полные видео (≥5 мин) | pytubefix | 2GB |

### Возможности бота

**Скачивание:**
- Автоматическое определение платформы по URL
- Адаптивное качество YouTube (720p для <60 мин, 480p для >60 мин)
- Fallback на RapidAPI при ошибках yt-dlp/pytubefix
- Извлечение аудио MP3 (320 kbps)

**Обработка видео:**
- Автоматическое исправление SAR/DAR (правильный aspect ratio)
- Faststart для мгновенного воспроизведения (moov atom в начале)
- YouTube thumbnail (превью как у конкурентов)
- Duration/width/height передаются явно в Telegram API

**Производительность:**
- Redis кэширование file_id (мгновенная повторная отправка)
- Local Bot API Server (лимит 2GB вместо 50MB)
- Метрики: время, размер, скорость скачивания

### Пайплайн обработки

```
URL → Определение платформы → Скачивание (video + audio)
    → Merge/Remux (ffmpeg -c copy) → fix_video (SAR)
    → ensure_faststart (moov) → download_thumbnail
    → sendVideo (duration/width/height/thumbnail/supports_streaming)
    → Cleanup
```

### Возможности админки (shadow-api.ru)

- Dashboard с метриками (боты, пользователи, скачивания)
- User Management (список, профили, активность)
- Broadcast System (массовые рассылки)
- Activity Logs (история действий)
- Error Tracking (логи ошибок по платформам)
- Bot Messages Editor (редактирование текстов)
- Performance Monitor (метрики скорости)
- API Usage Tracking (статистика провайдеров)

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    HOSTKEY (66.151.33.167)                  │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL :5432    Redis :6379    bot_manager             │
│       │                  │               │                  │
│       └──────────────────┴───────────────┘                  │
│                          │                                  │
│                   SaveNinja Bot                             │
│                   (@SaveNinja_bot)                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    AEZA (185.96.80.254)                     │
├─────────────────────────────────────────────────────────────┤
│  Nginx + SSL ──► Frontend (React)                           │
│       │                                                     │
│       └────────► API (FastAPI) :8000                        │
│                                                             │
│  Домены: shadow-api.ru, api.shadow-api.ru                   │
└─────────────────────────────────────────────────────────────┘
```

## Стек технологий

**Backend:**
- Python 3.12, FastAPI, SQLAlchemy 2.0 (async)
- PostgreSQL 16, Redis 7

**Frontend:**
- React 18 + TypeScript, Refine.dev, Ant Design 5, Vite

**Боты:**
- Aiogram 3, pytubefix, yt-dlp, RapidAPI, ffmpeg

**Инфраструктура:**
- Docker + Docker Compose
- Nginx (reverse proxy + SSL)
- GitHub Actions (CI/CD)
- Local Bot API Server (2GB limit)

## Быстрый старт

```bash
# Клонирование
git clone https://github.com/Malyugin777/telegrambots.git
cd telegrambots

# Настройка
cp infrastructure/.env.example infrastructure/.env
# Отредактируй .env

# Запуск
cd infrastructure
docker compose up -d --build
```

## Деплой

### Боты (Hostkey)
```bash
git push origin main
# GitHub Actions автоматически деплоит
```

### Админка (Aeza)
```bash
# Frontend
cd admin_panel/frontend && npm run build
scp -r dist/* root@185.96.80.254:/var/www/shadow-api/

# Backend
ssh root@185.96.80.254 "cd /root/admin_panel && docker compose up -d --build"
```

## Переменные окружения

```env
# Database
POSTGRES_USER=nexus
POSTGRES_PASSWORD=<password>
POSTGRES_DB=nexus_db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Bot
DOWNLOADER_BOT_TOKEN=<token>

# RapidAPI (для Instagram)
RAPIDAPI_KEY=<key>
RAPIDAPI_HOST=social-download-all-in-one.p.rapidapi.com

# API
JWT_SECRET=<secret>
```

## Структура проекта

```
TelegramBots/
├── infrastructure/           # Docker, конфиги
│   ├── docker-compose.yml
│   └── .env
├── bot_manager/              # Telegram боты
│   └── bots/
│       └── downloader/       # SaveNinja
│           ├── handlers/
│           │   └── download.py           # Основной handler
│           ├── services/
│           │   ├── downloader.py         # yt-dlp
│           │   ├── rapidapi_downloader.py # RapidAPI
│           │   ├── pytubefix_downloader.py # YouTube
│           │   └── cache.py              # Redis
│           └── messages.py
├── admin_panel/
│   ├── backend/              # FastAPI
│   └── frontend/             # React + Refine
└── shared/
    └── utils/
        └── video_fixer.py    # SAR/faststart/thumbnail
```

## FFmpeg обработка

| Операция | Команда | Когда |
|----------|---------|-------|
| Merge | `-c copy -bsf:v h264_metadata=sample_aspect_ratio=1/1 -movflags +faststart` | pytubefix adaptive |
| Faststart | `-c copy -movflags +faststart -fflags +genpts` | RapidAPI видео |
| SAR fix | `-vf scale=W:H,setsar=1:1 -c:v libx264` | Если SAR != 1:1 |
| Thumbnail | `-vf scale='min(320,iw)':-2 -q:v 5` | YouTube |

**Политика:** Без crop, без blur-fill, без принудительного 16:9.

## Полезные команды

```bash
# Логи ботов
ssh root@66.151.33.167 "docker logs nexus_bot_manager --tail 50"

# Логи админки
ssh root@185.96.80.254 "docker logs admin_api --tail 50"

# Перезапуск
ssh root@66.151.33.167 "cd /root/telegrambots/infrastructure && docker compose restart bot_manager"

# Подключение к БД
docker exec -it nexus_postgres psql -U nexus -d nexus_db
```

## Известные ограничения

| Проблема | Причина | Решение |
|----------|---------|---------|
| YouTube HTTP 500 | YouTube throttling | RapidAPI fallback |
| Долгое скачивание (>60 мин) | RapidAPI медленный | Progress updates |
| 4:3 видео "уже" | Не растягиваем | Правильное поведение |

## Лицензия

MIT
