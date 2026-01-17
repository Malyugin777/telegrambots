# TelegramBots

Система управления сетью Telegram-ботов с веб-админкой.

## SaveNinja Bot

**Username:** @SaveNinja_bot

Скачивание медиа из социальных сетей с автоматической конвертацией.

### Поддерживаемые платформы

| Платформа | Форматы | Движок |
|-----------|---------|--------|
| **Instagram** | Фото, видео, Reels, карусели, истории, актуальное | RapidAPI |
| **Pinterest** | Фото и видео | yt-dlp |
| **TikTok** | Видео без водяного знака | yt-dlp |
| **YouTube Shorts** | Короткие видео | yt-dlp |

### Возможности

- Автопроигрывание видео в Telegram
- Извлечение аудио MP3 (320 kbps)
- Автоматическое исправление SAR/DAR для корректного отображения
- Кэширование file_id в Redis (мгновенная повторная отправка)
- Максимальный размер файла: 50MB

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
- Aiogram 3, yt-dlp, RapidAPI, ffmpeg

**Инфраструктура:**
- Docker + Docker Compose
- Nginx (reverse proxy + SSL)
- GitHub Actions (CI/CD)

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
│           ├── services/
│           │   ├── downloader.py        # yt-dlp
│           │   ├── rapidapi_downloader.py  # RapidAPI
│           │   └── cache.py             # Redis
│           └── messages.py
├── admin_panel/
│   ├── backend/              # FastAPI
│   └── frontend/             # React + Refine
└── shared/                   # Общий код
```

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
