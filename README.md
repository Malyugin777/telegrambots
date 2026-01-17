# TelegramBots

Система управления сетью Telegram-ботов с веб-админкой.

## Боты

| Бот | Username | Описание |
|-----|----------|----------|
| SaveNinja | @SaveNinja_bot | Скачивание медиа из соцсетей |

### SaveNinja - Поддерживаемые платформы

| Платформа | Форматы | Движок |
|-----------|---------|--------|
| **Instagram** | Фото, видео, карусели, истории, актуальное | RapidAPI |
| **Pinterest** | Фото и видео | yt-dlp |
| **TikTok** | Видео без водяного знака | yt-dlp |
| **YouTube Shorts** | Короткие видео | yt-dlp |

## Архитектура

```
                         NGINX (порт 80/443)
                               |
          +--------------+--------------+
          |                             |
          v                             v
   Frontend (React)              API (FastAPI)
   Refine + Ant Design            /api/v1/...
                                       |
                        +--------------+--------------+
                        |                             |
                        v                             v
                   PostgreSQL                      Redis
                     :5432                         :6379
                        ^                             ^
                        |                             |
                        +-------------+---------------+
                                      |
                              Downloader Bot
                              (SaveNinja)
```

## Стек технологий

**Backend:**
- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async)
- PostgreSQL 16
- Redis 7

**Frontend:**
- React 18 + TypeScript
- Refine.dev (admin framework)
- Ant Design 5
- Vite

**Боты:**
- Aiogram 3
- yt-dlp (скачивание видео)
- ffmpeg (конвертация)
- FSM на Redis

**Инфраструктура:**
- Docker + Docker Compose
- Nginx (reverse proxy)
- GitHub Actions (CI/CD)

## Структура проекта

```
TelegramBots/
├── infrastructure/              # Docker, Nginx конфиги
│   ├── docker-compose.yml
│   ├── nginx/nginx.conf
│   └── .env
│
├── bot_net/                     # Telegram боты
│   ├── core/                    # Общий код ботов
│   │   ├── database/
│   │   └── utils/
│   └── bots/
│       └── downloader_bot/      # SaveNinja (@SaveNinja_bot)
│           ├── Dockerfile
│           ├── main.py
│           ├── config.py
│           ├── handlers/
│           ├── middlewares/
│           ├── services/
│           └── keyboards/
│
├── admin_panel/
│   ├── backend/                 # FastAPI API
│   │   └── src/
│   └── frontend/                # React + Refine
│       └── src/
│
└── shared/                      # Общая конфигурация
    └── config.py
```

## Быстрый старт

### 1. Клонирование

```bash
git clone <repo-url>
cd TelegramBots
```

### 2. Настройка окружения

```bash
cp infrastructure/.env.example infrastructure/.env
# Отредактируй .env - добавь токены ботов и пароли
```

### 3. Запуск

```bash
cd infrastructure
docker compose up -d --build
```

## Переменные окружения

Файл `infrastructure/.env`:

```env
# Database
POSTGRES_USER=nexus
POSTGRES_PASSWORD=<сгенерируй надёжный пароль>
POSTGRES_DB=nexus_db
DATABASE_URL=postgresql+asyncpg://nexus:<пароль>@postgres:5432/nexus_db

# Redis
REDIS_URL=redis://redis:6379/0

# Downloader Bot (SaveNinja)
DOWNLOADER_BOT_TOKEN=<токен от @BotFather>
FORCE_SUB_CHANNELS=@channel1,@channel2
MAX_FILE_SIZE_MB=50

# API
JWT_SECRET=<сгенерируй: openssl rand -hex 32>
CORS_ORIGINS=["https://admin.example.com"]
```

## Деплой

### Автоматический (GitHub Actions)

При пуше в `main` автоматически:
1. SSH на сервер
2. `git pull`
3. `docker compose down`
4. `docker compose up -d --build`

### Ручной

```bash
ssh user@server "cd /path/to/TelegramBots/infrastructure && git pull && docker compose up -d --build"
```

## Добавление нового бота

1. Создай папку `bot_net/bots/new_bot/`
2. Скопируй структуру из `downloader_bot`:
   ```
   new_bot/
   ├── Dockerfile
   ├── main.py
   ├── config.py
   ├── handlers/
   ├── middlewares/
   └── services/
   ```
3. Добавь сервис в `docker-compose.yml`
4. Добавь токен в `.env`: `NEW_BOT_TOKEN=...`
5. Деплой: `git push`

## API Endpoints

**Auth:**
- `POST /api/v1/auth/login` - получить JWT токен
- `POST /api/v1/auth/register` - регистрация админа

**Stats:**
- `GET /api/v1/stats` - статистика (users, bots, активность)
- `GET /api/v1/stats/load-chart` - график нагрузки

**Bots:**
- `GET /api/v1/bots` - список ботов
- `POST /api/v1/bots` - добавить бота
- `PATCH /api/v1/bots/{id}` - изменить статус

**Users:**
- `GET /api/v1/users` - список пользователей
- `PATCH /api/v1/users/{id}/ban` - забанить

**Broadcasts:**
- `GET /api/v1/broadcasts` - список рассылок
- `POST /api/v1/broadcasts` - создать рассылку

## Полезные команды

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker logs nexus_downloader --tail 100
docker logs nexus_api --tail 100

# Перезапуск сервиса
docker restart nexus_downloader

# Статус контейнеров
docker ps

# Подключение к БД
docker exec -it nexus_postgres psql -U nexus -d nexus_db
```

## GitHub Secrets

| Secret | Описание |
|--------|----------|
| SERVER_HOST | IP адрес сервера |
| SERVER_USER | SSH пользователь |
| SERVER_PASSWORD | SSH пароль |

## Сборка Frontend

Frontend собирается локально (если VPS не хватает RAM):

```bash
cd admin_panel/frontend
npm install
npm run build
git add dist/
git commit -m "build frontend"
git push
```

## TODO / Известные проблемы

- [ ] **Дублирование моделей БД** - модели в `admin_panel/backend/src/models.py` и `bot_net/core/database/models.py` нужно объединить в `shared/`
- [ ] **Дублирование конфига** - `shared/config.py` и `admin_panel/backend/src/config.py` с разными дефолтами
- [ ] **Миграции БД** - добавить Alembic вместо `create_all()`
- [ ] **Тесты** - добавить unit/integration тесты
- [ ] **N+1 запросы** - оптимизировать в `api/users.py` и `api/bots.py`
- [ ] **Health checks** - улучшить проверки в docker-compose
- [ ] **Кэширование** - добавить Redis кэш для статистики
- [ ] **Rate limiting** - добавить для API endpoints

