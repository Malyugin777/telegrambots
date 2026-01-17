# CLAUDE.md - Памятка для Claude

## Серверы

| Назначение | IP | Домен | Доступ |
|------------|----|----|--------|
| **Боты** | 66.151.33.167 | - | root / mcMdC3d+2b |
| **Админка** | 185.96.80.254 | shadow-api.ru | root / mcMdC3d+2b |

## Структура на серверах

### Сервер ботов (66.151.33.167)
```
/root/telegrambots/          # Git репо
  infrastructure/
    docker-compose.yml       # Все сервисы
    .env                     # Переменные
  bot_manager/               # Боты
  shared/                    # Общий код
```

**Docker контейнеры:**
- nexus_postgres (порт 5432)
- nexus_redis (порт 6379)
- nexus_bot_manager
- nexus_admin_api (порт 8000) - НЕ ИСПОЛЬЗУЕТСЯ, админка на другом сервере!
- nexus_admin_frontend (порт 80) - НЕ ИСПОЛЬЗУЕТСЯ

### Сервер админки (185.96.80.254 / shadow-api.ru)
```
/root/admin_panel/
  backend/                   # FastAPI API
    Dockerfile
  frontend/                  # React (исходники)
  docker-compose.yml         # Только API
  .env

/var/www/shadow-api/         # Собранный frontend (статика)
  index.html
  assets/
```

**Nginx:**
- https://shadow-api.ru -> /var/www/shadow-api (frontend)
- https://api.shadow-api.ru -> localhost:8000 (API в docker)

**Docker контейнеры:**
- admin_api (порт 8000)

**База данных:** подключается к PostgreSQL на 66.151.33.167!

## Деплой

### Боты (66.151.33.167)
```bash
ssh root@66.151.33.167 "cd /root/telegrambots && git pull && cd infrastructure && docker compose up -d --build"
```

### Админка frontend (185.96.80.254)
1. Собрать локально:
```bash
cd admin_panel/frontend
npm run build
```
2. Скопировать на сервер:
```bash
scp -r dist/* root@185.96.80.254:/var/www/shadow-api/
```

### Админка API (185.96.80.254)
```bash
ssh root@185.96.80.254 "cd /root/admin_panel && docker compose up -d --build"
```

## Учетные данные

### Админка (shadow-api.ru)
- **Логин:** admin
- **Пароль:** Admin123

### База данных
- **Host:** 66.151.33.167
- **User:** nexus
- **Password:** nexus_secure_pwd_2024
- **DB:** nexus_db

### Redis
- **Host:** 66.151.33.167
- **Port:** 6379

## Боты

| Бот | Username | Токен в .env |
|-----|----------|--------------|
| SaveNinja | @SaveNinja_bot | DOWNLOADER_BOT_TOKEN |

## API ключи

| Сервис | Переменная | Описание |
|--------|------------|----------|
| RapidAPI | RAPIDAPI_KEY | Social Download All In One - для Instagram |
| RapidAPI | RAPIDAPI_HOST | social-download-all-in-one.p.rapidapi.com |

**Загрузчики:**
- **Instagram** → RapidAPI (yt-dlp требует авторизации)
- **TikTok, YouTube, Pinterest** → yt-dlp (работает без авторизации)

## Частые проблемы

### VPS не хватает RAM для сборки frontend
На 66.151.33.167 добавлен swap 2GB:
```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
```

### Админка на shadow-api.ru не обновляется
Frontend - статика в /var/www/shadow-api/, нужно пересобрать и скопировать вручную.

### TikTok видео растянутые
Фикс в `bot_manager/bots/downloader/services/downloader.py` - re-encode через ffmpeg с SAR=1:1

### Pinterest качает placeholder
Парсинг через og:image мета-тег, фильтрация placeholder паттерна.
